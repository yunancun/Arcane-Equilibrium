"""P2-TEST-3a — unit tests for 4 pure helpers in misc_tools/.

Targets:
  - unique_list                  (bybit_h_stage_common.py)
  - bool_from_candidates         (bybit_h5_compat_helpers.py)
  - preview_text                 (bybit_h1_report_utils.py)
  - try_parse_json_object        (bybit_h1_report_utils.py)

Source files do dotted intra-directory imports (e.g. `from bybit_path_policy
import ...`), so we insert `program_code/.../misc_tools` onto sys.path before
importing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MISC_TOOLS = _ROOT / "program_code/exchange_connectors/bybit_connector/misc_tools"
if str(_MISC_TOOLS) not in sys.path:
    sys.path.insert(0, str(_MISC_TOOLS))

from bybit_h_stage_common import unique_list  # noqa: E402
from bybit_h5_compat_helpers import bool_from_candidates  # noqa: E402
from bybit_h1_report_utils import preview_text, try_parse_json_object  # noqa: E402


# ---------------------------------------------------------------------------
# unique_list
# ---------------------------------------------------------------------------

class TestUniqueList:
    def test_none_input_returns_empty_list(self):
        assert unique_list(None) == []

    def test_empty_input_returns_empty_list(self):
        assert unique_list([]) == []

    def test_scalar_dedup_preserves_first_occurrence_order(self):
        assert unique_list([1, 2, 1, 3, 2, 4]) == [1, 2, 3, 4]

    def test_string_dedup(self):
        assert unique_list(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_int_and_string_are_distinct_via_repr(self):
        # repr(1) == "1" while repr("1") == "'1'" — keys differ.
        assert unique_list([1, "1", 1, "1"]) == [1, "1"]

    def test_dict_dedup_uses_sorted_keys(self):
        # {"a":1,"b":2} and {"b":2,"a":1} must dedupe to a single entry.
        items = [{"a": 1, "b": 2}, {"b": 2, "a": 1}, {"a": 1, "b": 3}]
        out = unique_list(items)
        assert out == [{"a": 1, "b": 2}, {"a": 1, "b": 3}]

    def test_nested_list_dedup(self):
        items = [[1, 2], [1, 2], [2, 1], [1, 2, 3]]
        out = unique_list(items)
        assert out == [[1, 2], [2, 1], [1, 2, 3]]

    def test_mixed_dict_and_scalar(self):
        items = [{"a": 1}, "x", {"a": 1}, "x", 5]
        assert unique_list(items) == [{"a": 1}, "x", 5]

    def test_none_element_dedup(self):
        assert unique_list([None, None, 0, None]) == [None, 0]

    def test_bool_vs_int_are_distinguished_by_repr(self):
        # repr(True) == "True" while repr(1) == "1" — distinct keys.
        assert unique_list([True, 1, True, 1]) == [True, 1]


# ---------------------------------------------------------------------------
# bool_from_candidates
# ---------------------------------------------------------------------------

class TestBoolFromCandidates:
    def test_no_paths_returns_none(self):
        assert bool_from_candidates({"a": True}) is None

    def test_top_level_bool_true(self):
        assert bool_from_candidates({"flag": True}, "flag") is True

    def test_top_level_bool_false(self):
        assert bool_from_candidates({"flag": False}, "flag") is False

    def test_dotted_nested_path(self):
        doc = {"a": {"b": {"c": True}}}
        assert bool_from_candidates(doc, "a.b.c") is True

    def test_first_matching_path_wins(self):
        doc = {"first": False, "second": True}
        assert bool_from_candidates(doc, "first", "second") is False

    def test_missing_first_path_falls_through_to_second(self):
        doc = {"second": True}
        assert bool_from_candidates(doc, "missing.path", "second") is True

    def test_non_bool_value_is_skipped(self):
        # int 1 is not a bool; the helper requires `isinstance(cur, bool)`.
        doc = {"a": 1, "b": True}
        assert bool_from_candidates(doc, "a", "b") is True

    def test_string_value_returns_none(self):
        doc = {"flag": "true"}
        assert bool_from_candidates(doc, "flag") is None

    def test_returns_none_when_no_path_resolves(self):
        doc = {"a": {"b": 1}}
        assert bool_from_candidates(doc, "a.b.c", "x.y") is None

    def test_intermediate_non_dict_breaks_walk(self):
        # `a.b` is reachable but `a.b.c` walks into an int — break and skip.
        doc = {"a": {"b": 5}}
        assert bool_from_candidates(doc, "a.b.c") is None

    def test_empty_dict(self):
        assert bool_from_candidates({}, "anything", "a.b") is None

    def test_deeply_nested_false(self):
        doc = {"audit_summary": {"h2_stage_closed": False}}
        assert bool_from_candidates(doc, "audit_summary.h2_stage_closed") is False


# ---------------------------------------------------------------------------
# preview_text
# ---------------------------------------------------------------------------

class TestPreviewText:
    def test_none_returns_none(self):
        assert preview_text(None) is None

    def test_empty_string_returns_empty_string(self):
        assert preview_text("") == ""

    def test_under_default_limit_returned_unchanged(self):
        s = "x" * 100
        assert preview_text(s) == s

    def test_at_default_limit_returned_unchanged(self):
        s = "x" * 1600
        assert preview_text(s) == s

    def test_over_default_limit_truncated_with_suffix(self):
        s = "x" * 2000
        out = preview_text(s)
        assert out == "x" * 1600 + "...[truncated]"

    def test_custom_limit_at_boundary(self):
        assert preview_text("abcde", limit=5) == "abcde"

    def test_custom_limit_truncation(self):
        assert preview_text("abcdef", limit=3) == "abc...[truncated]"

    def test_non_string_input_is_stringified(self):
        # `str(value)` covers ints; len("12345") == 5, well under default limit.
        assert preview_text(12345) == "12345"

    def test_non_string_truncated_when_repr_exceeds_limit(self):
        # str(list) is long enough to test truncation path.
        big = list(range(1000))
        out = preview_text(big, limit=10)
        assert out is not None
        assert out.endswith("...[truncated]")
        assert len(out) == 10 + len("...[truncated]")


# ---------------------------------------------------------------------------
# try_parse_json_object
# ---------------------------------------------------------------------------

class TestTryParseJsonObject:
    def test_none_returns_none(self):
        assert try_parse_json_object(None) is None

    def test_empty_string_returns_none(self):
        assert try_parse_json_object("") is None

    def test_whitespace_only_returns_none(self):
        assert try_parse_json_object("   \n\t  ") is None

    def test_plain_json_object(self):
        assert try_parse_json_object('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}

    def test_nested_json_object(self):
        text = '{"outer": {"inner": [1, 2, 3]}, "flag": true}'
        assert try_parse_json_object(text) == {
            "outer": {"inner": [1, 2, 3]},
            "flag": True,
        }

    def test_json_array_returns_none(self):
        # Function explicitly requires `isinstance(obj, dict)`.
        assert try_parse_json_object("[1, 2, 3]") is None

    def test_json_scalar_returns_none(self):
        assert try_parse_json_object("42") is None
        assert try_parse_json_object('"hello"') is None

    def test_invalid_json_returns_none(self):
        assert try_parse_json_object("not json at all") is None
        assert try_parse_json_object("{broken") is None

    def test_json_code_fence_stripped(self):
        text = '```json\n{"a": 1}\n```'
        assert try_parse_json_object(text) == {"a": 1}

    def test_code_fence_without_language_tag(self):
        text = '```\n{"a": 2}\n```'
        assert try_parse_json_object(text) == {"a": 2}

    def test_code_fence_case_insensitive_language(self):
        text = '```JSON\n{"a": 3}\n```'
        assert try_parse_json_object(text) == {"a": 3}

    def test_whitespace_around_json_object(self):
        assert try_parse_json_object('   {"k": "v"}   ') == {"k": "v"}

    def test_non_string_input_stringified(self):
        # The function does `str(text).strip()` after the truthiness check.
        # Passing a dict-like object stringifies to its repr, which is not
        # valid JSON, so the result is None.
        assert try_parse_json_object({"a": 1}) is None

    def test_code_fence_containing_invalid_json_returns_none(self):
        assert try_parse_json_object("```json\nnope\n```") is None
