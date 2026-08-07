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


# Linux caps a *single* argv element at ``MAX_ARG_STRLEN`` = 32 * PAGE_SIZE
# (``include/uapi/linux/binfmts.h``), independently of the much larger total
# ``ARG_MAX``.  Measured read-only on the current runtime host ``trade-core`` on
# 2026-08-07 (Linux 6.17.0-35-generic x86_64, Ubuntu 24.04.4 LTS): PAGE_SIZE=4096,
# largest accepted single argv element = 131071 bytes => MAX_ARG_STRLEN = 131072
# = 32 * 4096; ARG_MAX = 2097152.
#
# These three numbers are the *recorded* trade-core observation.  They are NOT a
# portable constant: this development Mac reports SC_PAGESIZE=16384, where the
# same formula gives 524288.  So the test below derives the cap from the running
# kernel and only compares against the recorded value on Linux; asserting the
# recorded triple against itself would be a tautology that no host can fail.
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
        _FLAG, json.dumps({"schema_version": "context_artifact_v1"}),
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


def test_the_file_budget_survives_a_swap_after_the_size_check(tmp_path):
    """The budget must be enforced by the read, not by an earlier ``stat``.

    E2 demonstrated the first version accepting a 4,198,411-byte payload: the
    size was taken from ``stat`` and the parse then called an unbounded
    ``read_text``, so swapping the file in that window bypassed the budget
    entirely. The guard is only a guard if the bytes it admits are the bytes it
    measured.
    """

    path = tmp_path / "context.json"
    path.write_text("{}", encoding="utf-8")
    oversized = json.dumps({"pad": "x" * (governance.CONTEXT_ARTIFACT_MAX_BYTES + 4096)})
    real_stat = Path.stat
    swapped = {"done": False}

    def swap_after_stat(self, *args, **kwargs):
        result = real_stat(self, *args, **kwargs)
        if self == path and not swapped["done"]:
            swapped["done"] = True
            path.write_text(oversized, encoding="utf-8")
        return result

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(Path, "stat", swap_after_stat)
        with pytest.raises(ValueError, match="transport budget"):
            governance._context_artifact_arg(f"@{path}")
    finally:
        monkey.undo()
    assert swapped["done"], "the swap never happened; the test proved nothing"


# --------------------------------------------------------------------------- #
# the artifact is not the only ingress that carries a compiled Context
# --------------------------------------------------------------------------- #
def test_a_closure_packet_carries_a_context_artifact_and_is_size_guarded(tmp_path):
    """A closure packet embeds the whole artifact, so it is the larger payload.

    ``validate_closure`` reads ``dispatch.context_artifact``; the one real packet
    in-tree is 233,483 bytes around a 113,129-byte artifact, i.e. 1.78x the
    131072-byte single-argument cap. Fixing only ``--context-artifact`` would
    have left the bigger inline hazard open.
    """

    packet = {"schema_version": "closure_packet_v1", "pad": "y" * (32 * 1024)}
    inline = json.dumps(packet)
    assert len(inline.encode("utf-8")) > governance.INLINE_PAYLOAD_MAX_BYTES
    completed = _run(["closure", inline])
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "Traceback" not in completed.stderr, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any("above the" in error and "inline limit" in error
               for error in payload["errors"]), payload["errors"]

    # the same payload through @file is accepted by the transport layer and
    # refused on its own merits by the validator, not by the transport
    path = tmp_path / "closure.json"
    path.write_text(inline, encoding="utf-8")
    via_file = _run(["closure", f"@{path}"])
    assert "Traceback" not in via_file.stderr, via_file.stderr
    from_file = json.loads(via_file.stdout)
    assert not any("inline limit" in error for error in from_file["errors"])


def test_a_small_inline_closure_packet_is_still_accepted():
    """The size guard must not break the legitimate small-inline test callers."""

    completed = _run(["closure", json.dumps({"schema_version": "closure_packet_v1"})])
    assert "Traceback" not in completed.stderr, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"  # incomplete packet, but it was parsed
    assert not any("inline limit" in error for error in payload["errors"])


def test_the_real_in_tree_closure_packet_would_be_refused_inline():
    """Not a hypothetical: measure the packet this repo actually ships."""

    packet = ROOT / (
        "docs/execution_plan/ai_ml_landing/receipts/S1-closure-fix-2026-07-24/"
        "S1-closure-packet-v1.json"
    )
    if not packet.is_file():
        pytest.skip(f"the reference closure packet is absent: {packet}")
    size = packet.stat().st_size
    assert size > MEASURED_LINUX_MAX_ARG_STRLEN, size
    with pytest.raises(ValueError, match="inline limit"):
        governance._context_bearing_json_arg(
            packet.read_text(encoding="utf-8"), option="closure packet",
        )


def test_a_valid_at_file_context_artifact_still_reaches_the_callee(tmp_path):
    """The invariant must refuse inline transport without breaking the real path."""

    artifact = {"schema_version": "context_artifact_v1", "artifact_digest": "sha256:" + "0" * 64}
    path = tmp_path / "context.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    assert governance._context_artifact_arg(f"@{path}") == artifact


# --------------------------------------------------------------------------- #
# the caller inventory that justifies the "no active inline caller" branch
# --------------------------------------------------------------------------- #
# Three argument *shapes* rather than one mega-pattern.  An earlier draft looked
# only for a literal ``{``/``[`` next to the flag, which made every realistic
# programmatic caller invisible — ``json.dumps(artifact)``, a bare ``payload``
# variable, ``"$(cat context.json)"`` and ``"$CONTEXT_JSON"`` all passed.  The
# next draft flagged anything that was not an ``@`` path, which then flagged
# ordinary prose (the CLI's own error message begins with the flag name).
#
# Matching the shape instead keeps both properties: in real argv construction the
# flag is a *closed* token (a quoted argv element, or the equals spelling),
# whereas in prose it is the first word of a longer sentence.  The bare
# space-separated form is only meaningful in shell scripts, so it is scoped
# there.
# Composed at runtime rather than written literally.  The probes and patterns
# below are exactly what the sweep is built to flag, so spelling the flag out
# in them would make this file report itself as an offender.  Composing it keeps
# this module *inside* the sweep instead of buying a green run with an
# exclusion, which is the one place an inventory could be quietly hollowed out.
_FLAG = "--context-" + "artifact"

_CODE_ARG_RE = re.compile(r"""["']""" + _FLAG + r"""["']\s*[,)]\s*(?P<value>\S+)""")
_EQUALS_ARG_RE = re.compile(_FLAG + r"=(?P<value>\S+)")
_SHELL_ARG_RE = re.compile(_FLAG + r"\s+(?P<value>\S+)")
_AT_PATH_RE = re.compile(r"""^(?:[frbFRB]{0,2})?["']?@""")
_PLACEHOLDER_RE = re.compile(r"""^["']?<""")


def _value_is_legal_transport(value: str) -> bool:
    """Legal iff the value is an ``@path`` (any quoting) or a doc placeholder."""

    return bool(_AT_PATH_RE.match(value) or _PLACEHOLDER_RE.match(value))


def _inline_offenses(line: str, suffix: str) -> bool:
    """True when this line hands the flag something that is not an ``@path``."""

    patterns = [_CODE_ARG_RE, _EQUALS_ARG_RE]
    if suffix in {".sh", ".bash", ".zsh"}:
        patterns.append(_SHELL_ARG_RE)
    for pattern in patterns:
        match = pattern.search(line)
        if match and not _value_is_legal_transport(match.group("value")):
            return True
    return False
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
        if _FLAG not in text:
            continue
        inspected.append(relative)
        suffix = path.suffix.lower()
        for number, line in enumerate(text.splitlines(), start=1):
            if _inline_offenses(line, suffix):
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


def test_the_caller_inventory_detector_actually_detects_an_inline_caller():
    """Mutation guard: an inventory that can never fail proves nothing."""

    # Legal: an @path in any spelling, and the documented <placeholder>.
    assert not _inline_offenses(f"{_FLAG} @<context.json> -- <argv...>", ".sh")
    assert not _inline_offenses(f'"{_FLAG}", f"@{{context_file}}",', ".py")
    assert not _inline_offenses(f'"{_FLAG}", "@" + str(path),', ".py")
    assert not _inline_offenses(f"{_FLAG}=@/tmp/context.json", ".sh")
    # The argparse definition itself, and the CLI's own prose error message.
    assert not _inline_offenses(f'    "{_FLAG}",', ".py")
    assert not _inline_offenses(f'"{_FLAG} must be @<path-to-context.json>: "', ".py")

    # Regressions it must catch.  ``json.dumps(artifact)`` is listed here, not
    # under "legal": it is exactly the E2BIG path PR#129 took.  An earlier draft
    # of this test asserted it was fine, which would have forced anyone
    # strengthening the sweep to first delete an assertion blessing the bug.
    assert _inline_offenses(f'"{_FLAG}", json.dumps(artifact),', ".py")
    assert _inline_offenses(f'"{_FLAG}", "{{\\"a\\": 1}}",', ".py")
    assert _inline_offenses(f'{_FLAG}=[{{"role": "E2"}}]', ".py")
    assert _inline_offenses(f'{_FLAG} {{"schema_version": "x"}}', ".sh")
    assert _inline_offenses(f'{_FLAG} "$(cat context.json)"', ".sh")
    assert _inline_offenses(f'{_FLAG} "$CONTEXT_JSON"', ".sh")
    assert _inline_offenses(f'"{_FLAG}", payload,', ".py")
    assert _inline_offenses(f'"{_FLAG}", artifact_json)', ".py")


def test_the_textual_sweep_is_a_backstop_and_names_what_actually_proves_absence():
    """Be explicit about how much the grep can and cannot prove.

    A textual sweep can never prove the absence of an inline caller — it can
    only catch the shapes it knows. The guarantee comes from somewhere else:
    there is exactly one ingress for the artifact, and that ingress refuses
    every non-``@`` value at runtime regardless of how it was spelled. The sweep
    is a lint backstop that catches a regression at review time instead of at
    invocation time.
    """

    source = GOVERNANCE.read_text(encoding="utf-8")
    assert source.count("_context_artifact_arg(args.context_artifact)") == 1
    # whatever a caller writes, the loader is what decides
    for spelling in (
        '{"schema_version": "x"}',
        "$CONTEXT_JSON",
        "payload",
        " @/tmp/context.json",  # leading space => not an @path
    ):
        with pytest.raises(ValueError, match="must be @"):
            governance._context_artifact_arg(spelling)


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

    An earlier version of this test asserted ``131072 == 32 * 4096`` over three
    module constants. That can never fail on any host, so it proved nothing —
    and its own comment claimed a re-derivation it never performed. It is
    replaced by an actual derivation from the running kernel.
    """

    page_size = os.sysconf("SC_PAGESIZE")
    derived_cap = LINUX_MAX_ARG_STRLEN_PAGES * page_size

    # ARG_MAX (total argv+envp) is much larger and is *not* the binding limit;
    # confusing the two is what makes an inline payload look survivable.
    assert os.sysconf("SC_ARG_MAX") > derived_cap

    if sys.platform != "linux":
        # Apple Silicon is a documented deployment target and reports a 16 KiB
        # page, where the cap is 524288 rather than 131072. Pinning the recorded
        # Linux triple here would be wrong, not merely unportable.
        assert page_size > 0
        pytest.skip(
            f"single-argument cap is a Linux constant; this host is {sys.platform} "
            f"with SC_PAGESIZE={page_size} (derived cap {derived_cap}). The recorded "
            f"trade-core observation is {MEASURED_LINUX_MAX_ARG_STRLEN}."
        )
    assert page_size == MEASURED_LINUX_PAGE_SIZE, (
        f"this Linux host reports SC_PAGESIZE={page_size}, so MAX_ARG_STRLEN is "
        f"{derived_cap}, not the recorded {MEASURED_LINUX_MAX_ARG_STRLEN}; "
        "re-measure before relying on the recorded value"
    )
    assert derived_cap == MEASURED_LINUX_MAX_ARG_STRLEN


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
