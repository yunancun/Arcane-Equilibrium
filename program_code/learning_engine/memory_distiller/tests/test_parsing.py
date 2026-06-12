"""parsing 測試：兩段差異化 fail 策略（E2 審查重點 2 + mutation 錨 ①⑥ parser 半邊）。"""

from __future__ import annotations

import json

from program_code.learning_engine.memory_distiller.parsing import (
    parse_dedup_response,
    parse_extraction_response,
    strip_markdown_fence,
)

_ALLOWED = ["l2:l2r:a1", "drar:7"]


def _mem(**overrides) -> dict:
    base = {
        "content": "grid_trading 在低流動性 symbol 上滑點放大",
        "mem_type": "system_trait",
        "priority": 80,
        "source_ids": ["l2:l2r:a1"],
        "event_time_str": "",
        "metadata": {},
    }
    base.update(overrides)
    return base


def _extraction_json(memories: list[dict]) -> str:
    return json.dumps({"scene": "覆盤測試批", "memories": memories}, ensure_ascii=False)


# ── fence 剝除 ───────────────────────────────────────────────────────────────


def test_strip_fence_json_block():
    inner = '{"a": 1}'
    assert strip_markdown_fence(f"```json\n{inner}\n```") == inner


def test_strip_fence_plain_block_and_no_fence_idempotent():
    assert strip_markdown_fence("```\n[1]\n```") == "[1]"
    assert strip_markdown_fence('{"b": 2}') == '{"b": 2}'


# ── extraction：整批 fail-to-skip（錨 ⑥ parser 半邊）─────────────────────────


def test_extraction_valid_json_parsed():
    res = parse_extraction_response(_extraction_json([_mem()]), _ALLOWED)
    assert res.ok and len(res.memories) == 1
    assert res.scene == "覆盤測試批"
    assert res.memories[0].mem_type == "system_trait"


def test_extraction_fenced_json_parsed():
    res = parse_extraction_response(
        "```json\n" + _extraction_json([_mem()]) + "\n```", _ALLOWED
    )
    assert res.ok and len(res.memories) == 1


def test_extraction_invalid_json_fails_whole_batch():
    res = parse_extraction_response("這不是 JSON {", _ALLOWED)
    assert not res.ok
    assert res.memories == ()
    assert "extraction_json_invalid" in res.error


def test_extraction_non_object_fails():
    assert not parse_extraction_response("[1,2]", _ALLOWED).ok


def test_extraction_memories_not_list_fails():
    bad = json.dumps({"scene": "s", "memories": "oops"})
    assert not parse_extraction_response(bad, _ALLOWED).ok


def test_extraction_empty_memories_is_legitimate_success():
    res = parse_extraction_response(_extraction_json([]), _ALLOWED)
    assert res.ok and res.memories == ()


# ── extraction：單條白名單（寧缺毋濫，不殺整批）──────────────────────────────


def test_extraction_missing_content_dropped():
    res = parse_extraction_response(
        _extraction_json([_mem(content=""), _mem()]), _ALLOWED
    )
    assert res.ok and len(res.memories) == 1 and res.dropped_count == 1


def test_extraction_invalid_mem_type_dropped():
    res = parse_extraction_response(_extraction_json([_mem(mem_type="persona")]), _ALLOWED)
    assert res.ok and res.memories == () and res.dropped_count == 1


def test_extraction_priority_clamped_to_100():
    res = parse_extraction_response(_extraction_json([_mem(priority=999)]), _ALLOWED)
    assert res.ok and res.memories[0].priority == 100


def test_extraction_priority_non_numeric_dropped():
    res = parse_extraction_response(_extraction_json([_mem(priority="high")]), _ALLOWED)
    assert res.ok and res.memories == ()


def test_extraction_rule_minus_one_iron_rule_kept():
    res = parse_extraction_response(
        _extraction_json([_mem(mem_type="rule", priority=-1)]), _ALLOWED
    )
    assert res.ok and res.memories[0].priority == -1


def test_extraction_type_priority_floors_drop():
    # 分類型丟棄線：system_trait<50 / incident<60 / rule<70（R4 第二層）。
    res = parse_extraction_response(
        _extraction_json(
            [
                _mem(mem_type="system_trait", priority=49),
                _mem(mem_type="incident", priority=59),
                _mem(mem_type="rule", priority=69),
                _mem(mem_type="incident", priority=-1),  # -1 鐵則僅 rule 有效
            ]
        ),
        _ALLOWED,
    )
    assert res.ok and res.memories == () and res.dropped_count == 4


def test_extraction_source_ids_missing_or_empty_dropped():
    res = parse_extraction_response(
        _extraction_json([_mem(source_ids=[]), {"content": "x", "mem_type": "rule", "priority": 90}]),
        _ALLOWED,
    )
    assert res.ok and res.memories == () and res.dropped_count == 2


def test_extraction_source_ids_outside_materials_dropped():
    # R4 幻覺緩解：source_ids 必須可溯源到本批材料 id，越界=編造，整條丟棄。
    res = parse_extraction_response(
        _extraction_json([_mem(source_ids=["l2:l2r:made_up"])]), _ALLOWED
    )
    assert res.ok and res.memories == () and res.dropped_count == 1


# ── dedup：fail-open-to-store（錨 ①）────────────────────────────────────────

_RIDS = ["mem:n1", "mem:n2"]
_TARGETS = {"mem:n1": ["mem:old1", "mem:old2"], "mem:n2": ["mem:old3"]}


def test_dedup_valid_actions_parsed():
    rows = [
        {"record_id": "mem:n1", "action": "merge", "target_ids": ["mem:old1"],
         "merged_content": "合併後", "merged_type": "rule", "merged_priority": 85},
        {"record_id": "mem:n2", "action": "skip"},
    ]
    out = parse_dedup_response(json.dumps(rows), _RIDS, _TARGETS)
    assert [d.action for d in out] == ["merge", "skip"]
    assert out[0].target_ids == ("mem:old1",)
    assert out[0].merged_content == "合併後"
    assert out[0].merged_priority == 85
    assert not out[0].fail_open


def test_dedup_whole_batch_bad_json_all_store_fail_open():
    # mutation 錨 ①：壞 dedup JSON ⇒ 全 store（fail-open），絕不丟失新記憶。
    out = parse_dedup_response("not json at all", _RIDS, _TARGETS)
    assert [d.action for d in out] == ["store", "store"]
    assert all(d.fail_open for d in out)


def test_dedup_non_array_json_all_store():
    out = parse_dedup_response('{"record_id": "mem:n1"}', _RIDS, _TARGETS)
    assert [d.action for d in out] == ["store", "store"]


def test_dedup_invalid_action_falls_to_store():
    rows = [{"record_id": "mem:n1", "action": "delete_all"},
            {"record_id": "mem:n2", "action": "skip"}]
    out = parse_dedup_response(json.dumps(rows), _RIDS, _TARGETS)
    assert out[0].action == "store" and out[0].fail_open
    assert out[1].action == "skip"


def test_dedup_target_ids_out_of_candidates_falls_to_store():
    # target_ids 越界（不在該條關聯候選列表）⇒ 該條降 store（PA spec §13.1）。
    rows = [{"record_id": "mem:n1", "action": "update", "target_ids": ["mem:other"],
             "merged_content": "x", "merged_type": "rule"}]
    out = parse_dedup_response(json.dumps(rows), _RIDS, _TARGETS)
    assert out[0].action == "store" and out[0].fail_open


def test_dedup_merge_missing_merged_content_or_type_falls_to_store():
    rows = [
        {"record_id": "mem:n1", "action": "merge", "target_ids": ["mem:old1"],
         "merged_type": "rule"},
        {"record_id": "mem:n2", "action": "update", "target_ids": ["mem:old3"],
         "merged_content": "y", "merged_type": "bogus"},
    ]
    out = parse_dedup_response(json.dumps(rows), _RIDS, _TARGETS)
    assert [d.action for d in out] == ["store", "store"]
    assert all(d.fail_open for d in out)


def test_dedup_update_without_targets_falls_to_store():
    rows = [{"record_id": "mem:n1", "action": "update", "target_ids": [],
             "merged_content": "x", "merged_type": "rule"}]
    out = parse_dedup_response(json.dumps(rows), _RIDS, _TARGETS)
    assert out[0].action == "store" and out[0].fail_open


def test_dedup_missing_row_falls_to_store_and_order_preserved():
    rows = [{"record_id": "mem:n2", "action": "skip"}]  # 漏答 mem:n1
    out = parse_dedup_response(json.dumps(rows), _RIDS, _TARGETS)
    assert [d.record_id for d in out] == _RIDS  # 原序一一對應
    assert out[0].action == "store" and out[0].fail_open
    assert out[1].action == "skip"


def test_dedup_unknown_record_id_ignored():
    rows = [{"record_id": "mem:ghost", "action": "skip"}]
    out = parse_dedup_response(json.dumps(rows), _RIDS, _TARGETS)
    assert [d.action for d in out] == ["store", "store"]


def test_dedup_store_with_residual_targets_ignores_targets():
    # store/skip 不得攜帶 target（防誤 supersede）。
    rows = [{"record_id": "mem:n1", "action": "store", "target_ids": ["mem:old1"]},
            {"record_id": "mem:n2", "action": "skip"}]
    out = parse_dedup_response(json.dumps(rows), _RIDS, _TARGETS)
    assert out[0].target_ids == ()
