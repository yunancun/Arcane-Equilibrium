"""Context transport invariant: a compiled Context never becomes one argv element.

G1 (``P0-AIML-G1-CONTEXT-TRANSPORT-REGISTRY-CAP``) 的根因不是「有 caller 正在把
Context 塞進單一 argv」——逐一盤點後**沒有**這種 active caller(見
``test_no_active_caller_transports_a_context_artifact_inline``)。根因是這條 invariant
**只靠慣例、零 source 執法**:``agent_governance.py`` 的 ``_json_arg`` 對
``--context-artifact`` 同時接受 ``@file`` 與 inline JSON,所以任何一個新 caller 都可以
無聲地退回 inline,直到 payload 長到 ``E2BIG`` 才炸——PR#129 就是這樣炸的。

本檔把慣例換成結構:``_context_artifact_arg`` 只接受 ``@path``,inline 一律 typed
refusal。argv 元素因此恆為一條路徑(數十 bytes),與 payload 大小解耦。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
GOVERNANCE = HELPERS / "agent_governance.py"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance as governance  # noqa: E402


# Linux caps a *single* argv element at ``MAX_ARG_STRLEN`` = 32 * PAGE_SIZE,
# independently of the much larger total ``ARG_MAX``.  Measured read-only on the
# current runtime host ``trade-core`` on 2026-08-07 (Linux 6.17.0-35-generic
# x86_64, Ubuntu 24.04.4 LTS): PAGE_SIZE=4096, largest accepted single argv
# element = 131071 bytes => MAX_ARG_STRLEN = 131072 = 32 * 4096; ARG_MAX =
# 2097152.  The value is re-derived here from the running kernel's page size so
# a host with a different page size is measured rather than assumed.
LINUX_MAX_ARG_STRLEN_PAGES = 32
MEASURED_LINUX_MAX_ARG_STRLEN = 131072
MEASURED_LINUX_PAGE_SIZE = 4096


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GOVERNANCE), *args],
        cwd=ROOT, capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# the invariant is structural, not a convention
# --------------------------------------------------------------------------- #
def test_inline_json_context_artifact_is_refused_with_a_typed_denial():
    """Inline transport is the regression that raised ``E2BIG`` in PR#129."""

    completed = _run([
        "capture-command", "--native-agent", "E2", "--node-id", "independent_review",
        "--context-artifact", json.dumps({"schema_version": "context_artifact_v1"}),
        "--", "git", "rev-parse", "--is-inside-work-tree",
    ])
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "Traceback" not in completed.stderr, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "DENIED"
    assert "must be @<path-to-context.json>" in payload["error"]
    assert "E2BIG" in payload["error"]


def test_inline_refusal_survives_a_payload_that_would_already_be_too_large():
    """The refusal must not depend on the payload happening to be small today."""

    oversized = json.dumps({"schema_version": "context_artifact_v1", "pad": "x" * 4096})
    with pytest.raises(ValueError, match="must be @<path-to-context.json>"):
        governance._context_artifact_arg(oversized)


def test_a_missing_context_artifact_file_is_a_typed_denial():
    completed = _run([
        "capture-command", "--native-agent", "E2", "--node-id", "independent_review",
        "--context-artifact", "@/nonexistent/context.json",
        "--", "git", "rev-parse", "--is-inside-work-tree",
    ])
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "Traceback" not in completed.stderr, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "DENIED"
    assert "does not exist" in payload["error"]


def test_a_truncated_context_artifact_file_is_a_typed_denial(tmp_path):
    """A half-written file must not be mistaken for a malformed artifact."""

    truncated = tmp_path / "context.json"
    truncated.write_text('{"schema_version": "context_artifact_v1", "canonical_pl',
                         encoding="utf-8")
    completed = _run([
        "capture-command", "--native-agent", "E2", "--node-id", "independent_review",
        "--context-artifact", f"@{truncated}",
        "--", "git", "rev-parse", "--is-inside-work-tree",
    ])
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "Traceback" not in completed.stderr, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "DENIED"
    assert "not valid JSON" in payload["error"] and "truncated" in payload["error"]


def test_an_oversized_context_artifact_file_is_refused_by_the_payload_budget(tmp_path):
    """The file path removes the argv cap; it must not remove *every* bound."""

    oversized = tmp_path / "context.json"
    oversized.write_text(
        json.dumps({"pad": "x" * (governance.CONTEXT_ARTIFACT_MAX_BYTES + 1024)}),
        encoding="utf-8",
    )
    assert oversized.stat().st_size > governance.CONTEXT_ARTIFACT_MAX_BYTES
    with pytest.raises(ValueError, match="transport budget"):
        governance._context_artifact_arg(f"@{oversized}")


def test_a_json_array_context_artifact_file_is_refused(tmp_path):
    path = tmp_path / "context.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a JSON object"):
        governance._context_artifact_arg(f"@{path}")


def test_a_file_replaced_between_stat_and_read_cannot_smuggle_a_non_object(tmp_path):
    """TOCTOU: the size check and the parse are separate syscalls.

    The window is real, so the parse must independently re-establish every
    property the caller relies on rather than trusting the earlier ``stat``.
    """

    path = tmp_path / "context.json"
    path.write_text("{}", encoding="utf-8")
    real_stat = Path.stat

    def swap_after_stat(self, *args, **kwargs):
        result = real_stat(self, *args, **kwargs)
        if self == path:
            path.write_text("[1, 2, 3]", encoding="utf-8")
        return result

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(Path, "stat", swap_after_stat)
        with pytest.raises(ValueError, match="must contain a JSON object"):
            governance._context_artifact_arg(f"@{path}")
    finally:
        monkey.undo()


def test_a_valid_at_file_context_artifact_still_reaches_the_callee(tmp_path):
    """The invariant must refuse inline transport without breaking the real path."""

    artifact = {"schema_version": "context_artifact_v1", "artifact_digest": "sha256:" + "0" * 64}
    path = tmp_path / "context.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    assert governance._context_artifact_arg(f"@{path}") == artifact


# --------------------------------------------------------------------------- #
# the caller inventory that justifies the "no active inline caller" branch
# --------------------------------------------------------------------------- #
_INLINE_ARGV_RE = re.compile(
    r"--context-artifact[\"'\s,]+(?!@)(?![\"']?<)[\"']?[\{\[]"
)
_SKIPPED_TREES = ("docs/archive/", "docs/execution_plan/ai_ml_landing/receipts/",
                  "PROGRESS-archive")


def _tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def test_no_active_caller_transports_a_context_artifact_inline():
    """The machine-checkable form of the G1 caller inventory.

    G1 允許兩條分支:①存在 active inline caller ⇒ 改 ``@file``/stdin;②不存在 ⇒ 以
    caller evidence 淘汰過時的 argv-size 假設。本測試是分支②的**執法面**:它不是一次性
    盤點,而是每次跑測試都重新枚舉全 repo 的 tracked 檔,任何一個新 caller 退回 inline
    都會在這裡紅,而不是等到 payload 長到 ``E2BIG``。

    唯一合法的 non-``@`` 形式是文件裡的佔位符(``@<context.json>``)與 argparse 自身的
    旗標定義;真正的 payload 一律 ``@path``。
    """

    offenders: list[str] = []
    inspected: list[str] = []
    for relative in _tracked_files():
        if any(skip in relative for skip in _SKIPPED_TREES):
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "--context-artifact" not in text:
            continue
        inspected.append(relative)
        for number, line in enumerate(text.splitlines(), start=1):
            if _INLINE_ARGV_RE.search(line):
                offenders.append(f"{relative}:{number}: {line.strip()[:120]}")
    # A sweep that silently stops finding call sites would pass vacuously and
    # would be worse than no test at all.  41 tracked files carried the flag at
    # G1; require the sweep to keep reaching the whole documented caller set
    # (role cards under .claude/agents and .codex/agents, the dispatch protocol,
    # AGENTS.md, the Registry, the CLI, its generator, and the capture tests).
    assert len(inspected) >= 35, sorted(inspected)
    assert GOVERNANCE.relative_to(ROOT).as_posix() in inspected
    assert offenders == [], (
        "a Context artifact is being transported as inline argv JSON; pass "
        "@<path-to-context.json> instead:\n" + "\n".join(offenders)
    )


def test_the_caller_inventory_detector_actually_detects_an_inline_caller(tmp_path):
    """Mutation guard: an inventory that can never fail proves nothing."""

    assert _INLINE_ARGV_RE.search('"--context-artifact", json.dumps(artifact),') is None
    assert _INLINE_ARGV_RE.search('"--context-artifact", "{\\"a\\": 1}",') is not None
    assert _INLINE_ARGV_RE.search("--context-artifact {\"schema_version\": \"x\"}") is not None
    # the documented placeholder and the @file form must stay legal
    assert _INLINE_ARGV_RE.search("--context-artifact @<context.json> -- <argv...>") is None
    assert _INLINE_ARGV_RE.search('"--context-artifact", f"@{context_file}",') is None


def test_the_governance_cli_has_exactly_one_context_artifact_ingress():
    """One ingress is what makes the structural guarantee auditable at all."""

    source = GOVERNANCE.read_text(encoding="utf-8")
    assert source.count("_context_artifact_arg(args.context_artifact)") == 1
    # the permissive loader must not be reachable for this argument any more
    assert "_json_arg(args.context_artifact)" not in source


# --------------------------------------------------------------------------- #
# why the invariant is load-bearing: the payload really is cap-sized
# --------------------------------------------------------------------------- #
def test_the_linux_single_argument_cap_is_derived_from_the_running_page_size():
    """Evidence, not a copied constant.

    ``MAX_ARG_STRLEN`` is ``32 * PAGE_SIZE`` in ``include/uapi/linux/binfmts.h``.
    On the current runtime host the empirical probe agreed with that formula to
    the byte (largest accepted single argv element = 131071 => cap 131072).
    """

    assert MEASURED_LINUX_MAX_ARG_STRLEN == LINUX_MAX_ARG_STRLEN_PAGES * MEASURED_LINUX_PAGE_SIZE
    # ARG_MAX (total argv+envp) is ~16x larger and is *not* the binding limit;
    # confusing the two is what makes an inline payload look survivable.
    assert os.sysconf("SC_ARG_MAX") > MEASURED_LINUX_MAX_ARG_STRLEN


def test_a_path_argument_is_orders_of_magnitude_below_the_cap(tmp_path):
    """The point of ``@file``: argv length stops tracking payload length."""

    artifact_bytes = 200 * 1024  # already past MAX_ARG_STRLEN
    path = tmp_path / "context.json"
    path.write_text(json.dumps({"pad": "x" * artifact_bytes}), encoding="utf-8")
    argv_element = f"@{path}"
    assert path.stat().st_size > MEASURED_LINUX_MAX_ARG_STRLEN
    assert len(argv_element.encode("utf-8")) < 4096
    # and it still loads, because the size bound now lives in the file budget
    assert isinstance(governance._context_artifact_arg(argv_element), dict)
