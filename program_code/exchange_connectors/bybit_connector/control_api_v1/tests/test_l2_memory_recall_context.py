"""B3 L2 memory recall helper tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import l2_memory_recall_context as MRC


def _run(coro):
    return asyncio.run(coro)


def test_default_off_does_not_import_recall(monkeypatch):
    monkeypatch.delenv(MRC.ENV_L2_MEMORY_RECALL, raising=False)

    def _boom():
        raise AssertionError("recall import should not run when flag is off")

    monkeypatch.setattr(MRC, "_load_recall_for_prompt", _boom)
    ctx = _run(MRC.build_l2_memory_recall(symbol="BTCUSDT", context_hint="hint"))

    assert ctx.mode == "0"
    assert ctx.attempted is False
    assert ctx.record_ids == ()


def test_shadow_builds_audit_payload_without_prompt_injection(monkeypatch):
    monkeypatch.setenv(MRC.ENV_L2_MEMORY_RECALL, "shadow")

    async def _fake_recall(symbol, hint, *, char_budget, timeout_s):
        assert symbol == "BTCUSDT"
        assert "drawdown" in hint
        return SimpleNamespace(
            stable_block="- [rule] stable rule",
            recent_block="- [incident] recent incident",
            record_ids=["mem:r1", "mem:i1"],
            total_chars=50,
            degraded_level="fts",
        )

    monkeypatch.setattr(MRC, "_load_recall_for_prompt", lambda: _fake_recall)
    ctx = _run(MRC.build_l2_memory_recall(symbol="BTCUSDT", context_hint="drawdown"))

    assert ctx.mode == "shadow"
    assert ctx.should_audit() is True
    assert ctx.should_inject_prompt() is False
    assert ctx.audit_payload() == {
        "mode": "shadow",
        "record_ids": ["mem:r1", "mem:i1"],
        "total_chars": 50,
        "degraded_level": "fts",
    }
    sys_prompt, user_msg = MRC.apply_memory_recall_to_prompt(
        system_prompt="SYS", user_message="USER", recall=ctx
    )
    assert (sys_prompt, user_msg) == ("SYS", "USER")
    assert MRC.with_memory_recall_audit_context({"x": 1}, ctx)["memory_recall_shadow"][
        "record_ids"
    ] == ["mem:r1", "mem:i1"]


def test_active_mode_injects_prompt_and_keeps_audit_metadata():
    ctx = MRC.L2MemoryRecallContext(
        mode="1",
        attempted=True,
        record_ids=("mem:r1",),
        total_chars=20,
        degraded_level="vector",
        stable_block="- [rule] obey risk cap",
        recent_block="- [incident] avoid stale beta",
    )

    sys_prompt, user_msg = MRC.apply_memory_recall_to_prompt(
        system_prompt="SYS", user_message="USER", recall=ctx
    )

    assert "obey risk cap" in sys_prompt
    assert user_msg.startswith("Relevant recent memory")
    assert "avoid stale beta" in user_msg
    assert MRC.with_memory_recall_audit_context({"x": 1}, ctx)["memory_recall_shadow"][
        "degraded_level"
    ] == "vector"


def test_invalid_mode_disables(monkeypatch):
    monkeypatch.setenv(MRC.ENV_L2_MEMORY_RECALL, "yes")
    assert MRC.resolve_memory_recall_mode() == "0"


def test_recall_failure_is_fail_open_empty_audit(monkeypatch):
    monkeypatch.setenv(MRC.ENV_L2_MEMORY_RECALL, "shadow")

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(MRC, "_load_recall_for_prompt", lambda: _boom)
    ctx = _run(MRC.build_l2_memory_recall(symbol="BTCUSDT", context_hint="hint"))

    assert ctx.mode == "shadow"
    assert ctx.attempted is True
    assert ctx.record_ids == ()
    assert ctx.stable_block == ""
    assert ctx.recent_block == ""
