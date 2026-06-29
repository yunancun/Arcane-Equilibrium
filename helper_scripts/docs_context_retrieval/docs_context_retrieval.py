#!/usr/bin/env python3
"""CLI for read-only local docs context retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

try:
    from . import retriever
except ImportError:  # pragma: no cover
    _here = Path(__file__).resolve()
    if str(_here.parents[2]) not in sys.path:
        sys.path.insert(0, str(_here.parents[2]))
    from helper_scripts.docs_context_retrieval import retriever  # type: ignore


def _default_index_path() -> Path:
    return retriever.DEFAULT_OUTPUT_ROOT / "docs_context_index.json"


def _repo_root_arg(value: str | None) -> Path:
    return Path(value).resolve() if value else retriever.repo_root_from_here()


def _build(args: argparse.Namespace) -> int:
    index = retriever.build_index(
        repo_root=_repo_root_arg(args.repo_root),
        source_paths=args.source or None,
        chunk_line_count=args.chunk_lines,
        overlap_lines=args.overlap_lines,
    )
    out = Path(args.index_json or _default_index_path())
    retriever.write_index(index, out)
    print(json.dumps({
        "schema_version": index["schema_version"],
        "index_json": str(out),
        "index_sha256": index["index_sha256"],
        "chunk_count": index["chunk_count"],
        "source_count": len(index["source_fingerprints"]),
        "authority": index["authority"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _query(args: argparse.Namespace) -> int:
    index = retriever.load_index(Path(args.index_json or _default_index_path()))
    result = retriever.query_index(
        index,
        args.query,
        top_k=args.top_k,
        snippet_token_budget=args.snippet_token_budget,
    )
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _smoke(args: argparse.Namespace) -> int:
    index_path = Path(args.index_json or _default_index_path())
    index = retriever.build_index(
        repo_root=_repo_root_arg(args.repo_root),
        source_paths=args.source or None,
        chunk_line_count=args.chunk_lines,
        overlap_lines=args.overlap_lines,
    )
    retriever.write_index(index, index_path)
    queries = args.query or [
        "alpha evidence governance psr dsr pbo",
        "Decision Lease Rust authority",
        "ContextDistiller token cap",
    ]
    results = [
        retriever.query_index(index, query, top_k=args.top_k, snippet_token_budget=args.snippet_token_budget)
        for query in queries
    ]
    payload = {
        "schema_version": "tradebot.docs_context_retrieval.smoke.v1",
        "index_json": str(index_path),
        "index_sha256": index["index_sha256"],
        "query_count": len(results),
        "all_queries_returned_results": all(row["result_count"] > 0 for row in results),
        "authority": retriever.authority_flags(),
        "queries": results,
    }
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["all_queries_returned_results"] else 2


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docs_context_retrieval",
        description="Read-only offline BM25-style retrieval over TradeBot docs",
    )
    parser.add_argument("--repo-root", default=None, dest="repo_root")
    parser.add_argument("--source", action="append", default=[], help="Repo-relative file or directory to index")
    parser.add_argument("--index-json", default=None, dest="index_json")
    parser.add_argument("--chunk-lines", type=int, default=80, dest="chunk_lines")
    parser.add_argument("--overlap-lines", type=int, default=10, dest="overlap_lines")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-index")

    q = sub.add_parser("query")
    q.add_argument("--query", required=True)
    q.add_argument("--top-k", type=int, default=8, dest="top_k")
    q.add_argument("--snippet-token-budget", type=int, default=200, dest="snippet_token_budget")
    q.add_argument("--json-output", default=None, dest="json_output")

    smoke = sub.add_parser("smoke")
    smoke.add_argument("--query", action="append", default=[])
    smoke.add_argument("--top-k", type=int, default=5, dest="top_k")
    smoke.add_argument("--snippet-token-budget", type=int, default=160, dest="snippet_token_budget")
    smoke.add_argument("--json-output", default=None, dest="json_output")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.command == "build-index":
        return _build(args)
    if args.command == "query":
        return _query(args)
    if args.command == "smoke":
        return _smoke(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
