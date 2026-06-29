from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRV_ROOT = Path(__file__).resolve().parents[2]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from helper_scripts.docs_context_retrieval import retriever  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_index_and_query_returns_lineage(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "docs/adr/0047-alpha-edge-regime-evidence-governance.md",
        "# ADR 0047\n\nAlpha evidence requires PSR, DSR, PBO, OOS, fees, slippage, and regime breadth.\n",
    )
    _write(repo / "docs/README.md", "Decision Lease is not order authority.\n")

    index = retriever.build_index(repo_root=repo, source_paths=["docs"], chunk_line_count=20, overlap_lines=0)
    result = retriever.query_index(index, "alpha evidence psr dsr pbo", top_k=3)

    assert index["schema_version"] == retriever.INDEX_SCHEMA_VERSION
    assert index["authority"]["advisory_only"] is True
    assert index["authority"]["order_authority_granted"] is False
    assert result["schema_version"] == retriever.QUERY_SCHEMA_VERSION
    assert result["result_count"] >= 1
    first = result["results"][0]
    assert first["source_path"].endswith("0047-alpha-edge-regime-evidence-governance.md")
    assert first["line_start"] == 1
    assert first["line_span"] == [1, 3]
    assert first["score_semantics"] == "relevance_only"
    assert "PSR" in first["snippet"]
    assert result["authority"]["promotion_authority"] is False


def test_index_round_trip_preserves_schema(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "AGENTS.md", "PM first dispatch, E1 implementation, QA verification.\n")
    index = retriever.build_index(repo_root=repo, source_paths=["AGENTS.md"])
    path = tmp_path / "index.json"

    retriever.write_index(index, path)
    loaded = retriever.load_index(path)

    assert loaded["index_sha256"] == index["index_sha256"]
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == retriever.INDEX_SCHEMA_VERSION


def test_index_sha_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "docs/README.md", "Alpha evidence PSR DSR PBO.\n")

    first = retriever.build_index(repo_root=repo, source_paths=["docs"])
    second = retriever.build_index(repo_root=repo, source_paths=["docs"])

    assert first["index_sha256"] == second["index_sha256"]


def test_query_with_no_hits_is_advisory_empty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "docs/README.md", "Only local documentation is indexed.\n")
    index = retriever.build_index(repo_root=repo, source_paths=["docs"])

    result = retriever.query_index(index, "nonexistent-token-xyz", top_k=2)

    assert result["result_count"] == 0
    assert result["results"] == []
    assert result["authority"]["proof_authority"] is False


def test_build_index_respects_source_allowlist(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "docs/allowed.md", "alpha evidence PSR DSR PBO\n")
    _write(repo / "secrets/private.md", "never index this alpha token\n")

    index = retriever.build_index(repo_root=repo, source_paths=["docs"])
    result = retriever.query_index(index, "never index alpha token", top_k=5)

    assert {row["source_path"] for row in result["results"]} <= {"docs/allowed.md"}


def test_build_index_rejects_absolute_source_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside.md"
    _write(repo / "docs/allowed.md", "allowed docs\n")
    outside.write_text("secret outside repo\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source_path_outside_repo"):
        retriever.build_index(repo_root=repo, source_paths=[str(outside)])


def test_build_index_rejects_parent_directory_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "docs/allowed.md", "allowed docs\n")
    (tmp_path / "outside.md").write_text("secret outside repo\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source_path_outside_repo"):
        retriever.build_index(repo_root=repo, source_paths=["../outside.md"])


def test_empty_index_query_degrades_without_crash(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    index = retriever.build_index(repo_root=repo, source_paths=["missing"])

    result = retriever.query_index(index, "anything", top_k=3)

    assert index["chunk_count"] == 0
    assert result["result_count"] == 0
    assert result["authority"]["advisory_only"] is True


def test_snippet_token_budget_is_hard_cap(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "docs/README.md", "alpha beta gamma delta epsilon zeta eta theta iota kappa\n")
    index = retriever.build_index(repo_root=repo, source_paths=["docs"])

    result = retriever.query_index(index, "alpha beta gamma", top_k=1, snippet_token_budget=3)

    assert result["results"][0]["snippet_token_estimate"] <= 3
    assert len(retriever.tokenize(result["results"][0]["snippet"])) <= 3


def test_invalid_numeric_args_fail_fast(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "docs/README.md", "alpha beta\n")
    with pytest.raises(ValueError, match="chunk_line_count_must_be_positive"):
        retriever.build_index(repo_root=repo, source_paths=["docs"], chunk_line_count=0)
    with pytest.raises(ValueError, match="overlap_lines_must_be_less"):
        retriever.build_index(repo_root=repo, source_paths=["docs"], chunk_line_count=5, overlap_lines=5)

    index = retriever.build_index(repo_root=repo, source_paths=["docs"])
    with pytest.raises(ValueError, match="top_k_must_be_positive"):
        retriever.query_index(index, "alpha", top_k=0)
    with pytest.raises(ValueError, match="snippet_token_budget_must_be_positive"):
        retriever.query_index(index, "alpha", snippet_token_budget=0)
