#!/usr/bin/env python3
"""Classify changed paths for the hosted CI cost gates.

The classifier is intentionally stdlib-only so the first GitHub Actions job can
decide which expensive jobs are relevant before installing project dependencies.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable
from pathlib import Path
import sys


GATES = (
    "governance",
    "alr_fit_verifier",
    "rust",
    "schema",
    "stock_etf",
)

_CONTROL_PLANE_PATHS = {
    ".github/workflows/ci.yml",
    "helper_scripts/ci/classify_ci_changes.py",
}
_RUST_WORKSPACE_FILES = {"rust/Cargo.toml", "rust/Cargo.lock"}
_GIT_WORKFLOW_FILES = {
    "helper_scripts/maintenance_scripts/git_loop_guard.py",
    "tests/ci/test_classify_ci_changes.py",
    "tests/ci/test_github_ci_workflow_static.py",
    "tests/structure/test_git_loop_guard.py",
    "docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/"
    "2026-07-09--scanner_driven_alr/loop_contract.md",
    "docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/"
    "2026-07-09--scanner_driven_alr/startup_prompt.md",
}
_SCHEMA_PROBES = {
    "program_code/ml_training/tests/integration/"
    "alr_durable_fit_attestation_isolated_pg.py",
    "program_code/ml_training/tests/integration/"
    "alr_durable_fit_attestation_concurrency_isolated_pg.py",
    "program_code/ml_training/tests/integration/"
    "alr_atomic_fit_consumption_isolated_pg.py",
    "program_code/ml_training/tests/integration/"
    "alr_atomic_fit_consumption_concurrency_isolated_pg.py",
}


def _matches(
    path: str,
    *,
    exact: set[str] | frozenset[str] = frozenset(),
    prefixes: tuple[str, ...] = (),
) -> bool:
    return path in exact or path.startswith(prefixes)


def classify_paths(paths: Iterable[str], *, force_all: bool = False) -> dict[str, bool]:
    """Return the expensive CI gates required by *paths*."""

    result = {gate: bool(force_all) for gate in GATES}
    if force_all:
        return result

    for raw_path in paths:
        path = raw_path
        if not path:
            continue
        if path in _CONTROL_PLANE_PATHS:
            return {gate: True for gate in GATES}

        if _matches(
            path,
            exact={"AGENTS.md", "CLAUDE.md", "CONTEXT.md"} | _GIT_WORKFLOW_FILES,
            prefixes=(
                ".agents/skills/",
                ".codex/",
                ".claude/",
                "docs/adr/",
                "docs/amd/",
                "docs/agents/",
                "docs/governance_dev/",
                "helper_scripts/maintenance_scripts/",
                "tests/structure/test_agent_governance_",
                "tests/structure/test_development_agent_governance.py",
                "tests/migrations/test_v158_",
                "tests/migrations/test_v159_",
                "sql/migrations/V158__",
                "sql/migrations/V159__",
            ),
        ):
            result["governance"] = True

        if _matches(
            path,
            exact=_RUST_WORKSPACE_FILES | {"tests/structure/test_alr_fit_verifier_source_static.py"},
            prefixes=("rust/openclaw_alr_fit_verifier/",),
        ):
            result["alr_fit_verifier"] = True

        if path.startswith("rust/"):
            result["rust"] = True

        if _matches(
            path,
            exact=_RUST_WORKSPACE_FILES | _SCHEMA_PROBES,
            prefixes=(
                "sql/migrations/",
                "rust/openclaw_engine/",
                "rust/openclaw_types/",
            ),
        ):
            result["schema"] = True

        # stock_etf gate 觸發面（含 IBKR lane）：除既有 control_api Python 邊界外，
        # 純 rust / 純 structure-test 的 PR 過去不觸發本 gate → hosted CI 連 job 都被
        # skip（G0.5 當年 CI drift 病根）。此處補齊 rust handler/tests、openclaw_types
        # 的 ibkr_/stock_etf_ 型別檔、以及 tests/structure 的 stock_etf/ibkr 守衛前綴。
        if _matches(
            path,
            prefixes=(
                "program_code/exchange_connectors/bybit_connector/control_api_v1/",
                "tests/structure/test_stock_etf_",
                "tests/structure/test_ibkr_",
                "rust/openclaw_engine/src/ipc_server/handlers/stock_etf",
                "rust/openclaw_engine/src/ipc_server/tests/stock_etf",
                "rust/openclaw_types/src/ibkr_",
                "rust/openclaw_types/src/stock_etf_",
            ),
        ):
            result["stock_etf"] = True

    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--null",
        action="store_true",
        help="read NUL-delimited paths (for git diff --name-only -z)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="force_all",
        help="enable every gate (used for push and schedule events)",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        help="append key=value records to this GitHub Actions output file",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    raw = sys.stdin.buffer.read()
    records = raw.split(b"\0") if args.null else raw.splitlines()
    paths = [os.fsdecode(record) for record in records if record]
    result = classify_paths(paths, force_all=args.force_all)
    rendered = "".join(f"{gate}={'true' if result[gate] else 'false'}\n" for gate in GATES)

    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
