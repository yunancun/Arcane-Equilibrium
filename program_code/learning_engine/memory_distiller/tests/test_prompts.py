"""prompts builder 純函數快照測試（PA spec §13.1 prompts 行）。"""

from __future__ import annotations

from program_code.learning_engine.memory_distiller.prompts import (
    CONFLICT_DETECTION_SYSTEM_PROMPT,
    EXTRACT_MEMORIES_SYSTEM_PROMPT,
    MATERIAL_TEXT_MAX_CHARS,
    TRUNCATION_MARKER,
    Material,
    format_batch_dedup_prompt,
    format_extraction_prompt,
    truncate_text,
)


def _mat(mid: str = "l2:l2r:abc123", kind: str = "l2_call", text: str = "x") -> Material:
    return Material(material_id=mid, source_kind=kind, ts_iso="2026-06-10T03:00:00+00:00", text=text)


# ── system prompt 常數（checked-in 模板關鍵不變式）──────────────────────────


def test_extraction_system_prompt_pins_three_mem_types():
    for token in ("system_trait", "incident", "rule"):
        assert token in EXTRACT_MEMORIES_SYSTEM_PROMPT
    # 交易語義三類是拍板改造；上游 persona/episodic/instruction 不得殘留。
    for legacy in ("persona", "episodic", "instruction"):
        assert legacy not in EXTRACT_MEMORIES_SYSTEM_PROMPT


def test_extraction_system_prompt_requires_source_ids_and_json():
    assert "source_ids" in EXTRACT_MEMORIES_SYSTEM_PROMPT
    assert "嚴禁編造" in EXTRACT_MEMORIES_SYSTEM_PROMPT
    assert '"memories"' in EXTRACT_MEMORIES_SYSTEM_PROMPT


def test_dedup_system_prompt_pins_four_actions_and_target_constraint():
    for token in ('"store"', '"skip"', '"update"', '"merge"'):
        assert token in CONFLICT_DETECTION_SYSTEM_PROMPT
    assert "target_ids" in CONFLICT_DETECTION_SYSTEM_PROMPT
    assert "關聯候選 ID" in CONFLICT_DETECTION_SYSTEM_PROMPT


# ── 截斷 ─────────────────────────────────────────────────────────────────────


def test_truncate_short_text_unchanged():
    assert truncate_text("短文本") == "短文本"


def test_truncate_long_text_capped_with_marker():
    long = "a" * (MATERIAL_TEXT_MAX_CHARS + 500)
    out = truncate_text(long)
    assert len(out) <= MATERIAL_TEXT_MAX_CHARS
    assert out.endswith(TRUNCATION_MARKER)


def test_truncate_idempotent_no_double_marker():
    once = truncate_text("b" * (MATERIAL_TEXT_MAX_CHARS + 1))
    twice = truncate_text(once)
    assert twice == once


def test_truncate_none_returns_empty():
    assert truncate_text(None) == ""


# ── extraction builder ───────────────────────────────────────────────────────


def test_extraction_prompt_declares_utc_header():
    out = format_extraction_prompt([_mat()])
    assert "UTC" in out
    assert "ISO 8601" in out


def test_extraction_prompt_material_line_format_l2_and_drar():
    out = format_extraction_prompt(
        [
            _mat(mid="l2:l2r:abc123", kind="l2_call", text="呼叫摘要"),
            _mat(mid="drar:42", kind="drar_postmortem", text="taxonomy=no_edge"),
        ]
    )
    assert "[l2:l2r:abc123] [l2_call] [2026-06-10T03:00:00+00:00]: 呼叫摘要" in out
    assert "[drar:42] [drar_postmortem]" in out


def test_extraction_prompt_truncates_material_text():
    out = format_extraction_prompt([_mat(text="c" * (MATERIAL_TEXT_MAX_CHARS + 999))])
    assert TRUNCATION_MARKER in out
    assert "c" * (MATERIAL_TEXT_MAX_CHARS + 1) not in out


# ── dedup builder ────────────────────────────────────────────────────────────


def test_dedup_prompt_contains_pool_and_related_ids():
    new = [{"record_id": "mem:n1", "content": "新記憶", "mem_type": "rule", "priority": 90}]
    pool = [{"record_id": "mem:old1", "content": "舊記憶", "mem_type": "rule", "priority": 80}]
    out = format_batch_dedup_prompt(new, pool, {"mem:n1": ["mem:old1"]})
    assert "統一候選記憶池" in out
    assert "mem:old1" in out
    assert "mem:n1" in out
    assert "【關聯候選 ID】" in out


def test_dedup_prompt_deterministic():
    new = [{"record_id": "mem:n1", "content": "x", "mem_type": "incident", "priority": 60}]
    pool = [{"record_id": "mem:p1", "content": "y", "mem_type": "rule", "priority": 70}]
    related = {"mem:n1": ["mem:p1"]}
    assert format_batch_dedup_prompt(new, pool, related) == format_batch_dedup_prompt(
        new, pool, related
    )
