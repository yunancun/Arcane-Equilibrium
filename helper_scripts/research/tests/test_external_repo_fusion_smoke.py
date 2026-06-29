from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

SRV_ROOT = Path(__file__).resolve().parents[3]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from helper_scripts.research.external_repo_fusion_smoke import run_smoke, scratch_root  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_external_repo_fusion_smoke_wires_retrieval_and_audits(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "AGENTS.md", "PM first dispatch and QA verification.\n")
    _write(repo / "CLAUDE.md", "Decision Lease is not order authority. no order no bybit no pg advisory.\n")
    _write(repo / ".codex/MEMORY.md", "ContextDistiller token cap and docs retrieval memory.\n")
    _write(
        repo / "docs/adr/0047-alpha-edge-regime-evidence-governance.md",
        "Alpha evidence governance requires PSR DSR PBO OOS cost_bps slippage fee regime breadth n_independent sample_unit advisory_only order_authority_granted false promotion_proof false recent_90d.\n",
    )
    _write(
        repo / "docs/adr/0045-m4-hypothesis-discovery-governance.md",
        "M4 hypothesis draft status exploratory not live no order. n_observations shift(1) leak-free forward OOS Bonferroni alpha_corrected cohens_d subperiod stability graveyard.\n",
    )
    _write(
        repo / "helper_scripts/m4/attribute_enforcer.py",
        "def gate():\n    return 'preregistered'  # not live no order bonferroni shift(1) leak-free\n",
    )
    _write(
        repo / "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--external_repo_integration_synthesis.md",
        "status ready\nartifact path `/tmp/x.json` sha abc123\nno order no bybit no pg advisory\nverification pytest passed\nnext operator handoff\n",
    )

    output_dir = scratch_root() / f"external_repo_fusion_smoke_pytest_{os.getpid()}"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    try:
        summary = run_smoke(
            repo_root=repo,
            output_dir=output_dir,
            queries=["alpha evidence PSR DSR PBO", "Decision Lease order authority", "ContextDistiller token cap"],
        )

        assert summary["status"] == "EXTERNAL_REPO_FUSION_SMOKE_COMPLETE"
        assert summary["retrieval_ready"] is True
        assert summary["audit_emitted"] is True
        assert summary["authority_preserved"] is True
        assert Path(summary["docs_index_json"]).exists()
        assert Path(summary["output_dir"]).is_relative_to(scratch_root())
        smoke_summary = output_dir / "external_repo_fusion_smoke_summary.json"
        assert json.loads(smoke_summary.read_text(encoding="utf-8"))["schema_version"] == summary["schema_version"]
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_external_repo_fusion_smoke_rejects_non_openclaw_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "AGENTS.md", "PM first dispatch.\n")

    with pytest.raises(ValueError, match="output_dir_must_be_under_tmp_openclaw"):
        run_smoke(repo_root=repo, output_dir=tmp_path / "out")
