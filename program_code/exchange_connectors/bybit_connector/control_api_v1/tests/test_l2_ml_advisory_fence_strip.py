"""
Item 8（E4 focused regression）— L2 ml_advisory fence-strip + stage 分類的純字串/解析單元測試。
Item 8 (E4 focused regression) — pure string/parse unit test for the L2 ml_advisory
fence-strip and stage classification logic.

為什麼要這支獨立測試（互補於 test_l2_p3a_ml_advisory.py 的 cascade 級測試）：
  test_l2_p3a_ml_advisory.py 經整條 async cascade（含 orchestrator import → tomllib，需 py3.11+）
  驗 stage=parse_failed / cloud_unavailable；本檔只 import executor 模組本身（不碰 orchestrator），
  對「剝殼」與「stage 分類」的最小可證偽核心做**純字串/解析**斷言——無網路、無 SDK、無 DB。
Why a separate focused file: the cascade-level file imports the orchestrator (needs py3.11 tomllib);
this file imports ONLY the executor and asserts the smallest falsifying core of the item-8 change
(fence-strip + honest stage split) with pure string/parse logic — no network, no SDK, no DB.

覆蓋 / coverage：
  1. _extract_json_object_text：剝 ```json / ``` fence + 前後散文，抽出 '{...}' 子字串。
  2. _parse_cloud_reply_json：剝殼後 json.loads，回 dict；非 dict / 壞 JSON / 無殼 → None。
  3. _run_cloud_interpret 的 stage 分類（用 stub engine，只 stub IO 邊界 _provider_complete，
     不 stub 任何業務邏輯；§5.1 允許 stub IO）：
       - provider 回 None（真 outage）→ cloud_stage="cloud_unavailable"
       - 有回覆且可 parse → cloud_stage="ok"
       - 有回覆但無法 parse（present-but-unparsable）→ cloud_stage="parse_failed"（**絕不** outage）
     這是誠實邊界：present-but-unparsable 永遠不得被標成 cloud_unavailable。

Mac-tested（純邏輯 + stubbed IO 邊界；無真 model / 無真 DB / 無網路）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ── sys.path：加 control_api_v1 root（app.*）+ program_code / srv root（executor 的
#    ml_training.advisory_review_packet import 的兩條解析路徑）。與姊妹測試同慣例。──
# sys.path setup: control_api_v1 root for `app.*`, plus program_code/srv-root so the
# executor's `ml_training.advisory_review_packet` import (either spelling) resolves.
_HERE = Path(__file__).resolve()
_CONTROL_API_ROOT = _HERE.parents[1]      # .../control_api_v1
_PROGRAM_CODE = _HERE.parents[4]          # .../program_code（讓 `ml_training` 可 import）
_SRV_ROOT = _HERE.parents[5]              # .../srv（讓 `program_code.ml_training` fallback 可 import）
for _p in (_CONTROL_API_ROOT, _PROGRAM_CODE, _SRV_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app import l2_ml_advisory_executor as EXEC  # noqa: E402


# 合法診斷輸出（stage=ok 分支 + 剝殼後 parse 成 dict 的斷言用）。
# A valid diagnose payload (used to assert the ok stage + fence-strip → dict).
_VALID_DIAGNOSE_OUTPUT: dict[str, Any] = {
    "mode": "diagnose_leak",
    "leak_drift_diagnosis": {
        "suspected_cause": "future-return leak",
        "evidence": [
            {"claim": "feature name matches forbidden pattern", "kind": "leak",
             "source_ref": "leakage_check", "source_class": "name_pattern_check"}
        ],
        "recommended_check": "run shift1_compliance",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1) _extract_json_object_text — 純剝殼（fence + 前後散文 → '{...}' 子字串）
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractJsonObjectText:
    def test_fenced_json_lang_tag(self):
        """```json fence → 剝出內層 '{...}'。 / ```json fence → inner object text."""
        raw = '```json\n{"a": 1}\n```'
        assert EXEC._extract_json_object_text(raw) == '{"a": 1}'

    def test_fenced_no_lang_tag(self):
        """無語言標的 ``` fence 亦剝。 / bare ``` fence (no lang) is stripped too."""
        raw = '```\n{"a": 1}\n```'
        assert EXEC._extract_json_object_text(raw) == '{"a": 1}'

    def test_fenced_uppercase_lang_tag_ignorecase(self):
        """```JSON（大寫）→ IGNORECASE 仍剝。 / uppercase ```JSON stripped via IGNORECASE."""
        raw = '```JSON\n{"a": 1}\n```'
        assert EXEC._extract_json_object_text(raw) == '{"a": 1}'

    def test_prose_before_and_after_fence(self):
        """fence 前後夾散文 → 只回內層 object（吃掉「Here is:」「Hope this helps.」）。
        Prose wrapping the fence is discarded; only the inner object is returned."""
        raw = "Here is the analysis:\n```json\n{\"a\": 1}\n```\nHope this helps."
        assert EXEC._extract_json_object_text(raw) == '{"a": 1}'

    def test_bare_object_no_fence(self):
        """無 fence 的裸 object → 原樣回。 / bare object (no fence) returned as-is."""
        raw = '{"a": 1}'
        assert EXEC._extract_json_object_text(raw) == '{"a": 1}'

    def test_prose_wrapped_bare_object_no_fence(self):
        """無 fence 但前後夾散文 → 取第一個 '{' 到最後一個 '}'。
        No fence but prose around a bare object → first '{' .. last '}'."""
        raw = 'Result: {"a": 1} done'
        assert EXEC._extract_json_object_text(raw) == '{"a": 1}'

    def test_nested_braces_preserved(self):
        """巢狀花括號 → 取第一 '{' 到最後 '}'，內層結構完整保留。
        Nested braces → first '{' to last '}', inner structure preserved."""
        raw = 'x {"a": {"b": 2}} y'
        assert EXEC._extract_json_object_text(raw) == '{"a": {"b": 2}}'

    def test_empty_string_returns_none(self):
        """空字串 → None（交呼叫端判 parse_failed，非 outage）。 / empty → None."""
        assert EXEC._extract_json_object_text("") is None

    def test_whitespace_only_returns_none(self):
        """純空白 → strip 後無花括號 → None。 / whitespace only → None."""
        assert EXEC._extract_json_object_text("   \n\t  ") is None

    def test_prose_without_braces_returns_none(self):
        """無花括號的散文 → None（不誤把裸字當 JSON）。 / prose w/o braces → None."""
        assert EXEC._extract_json_object_text("Sorry, no structured output.") is None

    def test_closing_before_opening_returns_none(self):
        """'}' 在 '{' 之前（end < start）→ None（守 degenerate 序）。
        A '}' before '{' (end < start) → None."""
        assert EXEC._extract_json_object_text("} then {") is None

    def test_empty_fence_body_returns_none(self):
        """fence 內為空 → 剝後無花括號 → None。 / empty fenced body → None."""
        assert EXEC._extract_json_object_text("```json\n\n```") is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2) _parse_cloud_reply_json — 剝殼後 json.loads → dict（非 dict / 壞 JSON → None）
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseCloudReplyJson:
    def test_fenced_valid_dict_parses_with_values(self):
        """帶 ```json fence + 散文的合法回覆 → parse 成 dict，值完整保留。
        Fenced + prose-wrapped valid reply → dict with values preserved."""
        raw = (
            "Here is the diagnosis you asked for:\n\n"
            "```json\n" + json.dumps(_VALID_DIAGNOSE_OUTPUT) + "\n```\n\n"
            "Hope this helps."
        )
        parsed = EXEC._parse_cloud_reply_json(raw)
        assert isinstance(parsed, dict)
        assert parsed == _VALID_DIAGNOSE_OUTPUT  # 值等價（非只型別）

    def test_bare_dict_parses(self):
        """裸 dict（無 fence）→ dict。 / bare dict (no fence) → dict."""
        parsed = EXEC._parse_cloud_reply_json('{"mode": "diagnose_leak", "n": 3}')
        assert parsed == {"mode": "diagnose_leak", "n": 3}

    def test_prose_wrapped_bare_dict_parses(self):
        """無 fence 但夾散文的 dict → dict。 / prose-wrapped bare dict → dict."""
        parsed = EXEC._parse_cloud_reply_json('Analysis: {"ok": true, "k": 1} end')
        assert parsed == {"ok": True, "k": 1}

    def test_toplevel_array_no_braces_returns_none(self):
        """頂層 JSON 陣列（無花括號）→ None（本路徑契約恆回單一 object，非 array）。
        Top-level JSON array w/o braces → None (contract returns a single object)."""
        assert EXEC._parse_cloud_reply_json("[1, 2, 3]") is None

    def test_malformed_json_in_fence_returns_none(self):
        """fence 內壞 JSON → None（present-but-unparsable；交呼叫端判 parse_failed）。
        Malformed JSON inside fence → None (present-but-unparsable → parse_failed)."""
        assert EXEC._parse_cloud_reply_json("```json\n{bad json}\n```") is None

    def test_trailing_comma_invalid_returns_none(self):
        """尾逗號（strict JSON 非法）→ None。 / trailing comma (invalid JSON) → None."""
        assert EXEC._parse_cloud_reply_json('{"a": 1,}') is None

    def test_empty_returns_none(self):
        """空字串 → None。 / empty → None."""
        assert EXEC._parse_cloud_reply_json("") is None

    def test_prose_only_returns_none(self):
        """純散文（無 JSON）→ None（present-but-unparsable）。 / prose only → None."""
        assert EXEC._parse_cloud_reply_json("I cannot produce structured output.") is None

    def test_nested_dict_values_roundtrip(self):
        """巢狀 dict 值往返一致（parse 非破壞性）。 / nested dict values round-trip."""
        payload = {"mode": "interpret_result", "d": {"x": [1, 2], "y": {"z": True}}}
        raw = "```json\n" + json.dumps(payload) + "\n```"
        assert EXEC._parse_cloud_reply_json(raw) == payload


# ═══════════════════════════════════════════════════════════════════════════════
# 3) stage 分類（誠實邊界）— 用 stub engine 直驅真 _run_cloud_interpret（無網路/SDK）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 只 stub IO 邊界（engine._provider_complete = 假回應），不 stub 任何業務邏輯（剝殼/分類真跑）。
# 這是 §5.1 允許的 IO stub，且驗的是**真** stage 分類碼，非鏡像重寫。
# We stub only the IO boundary (engine._provider_complete); the real strip/classify code runs.


class _StubResponse:
    def __init__(self, text: str, in_tok: int = 5, out_tok: int = 7):
        self.text = text
        self.input_tokens = in_tok
        self.output_tokens = out_tok


class _StubConfig:
    default_provider = "anthropic"


class _StubCostTracker:
    def get_config(self):
        return _StubConfig()

    def record_claude_cost(self, session, in_tok, out_tok, model_tier):
        return 0.01  # 確定性小額（stage 分類與此無關，只為讓記帳路徑不崩）


class _StubEngine:
    """只 stub IO 邊界的假 engine：_provider_complete 回固定文本（reply_text=None → 模擬 outage）。
    IO-boundary-only stub engine: _provider_complete returns fixed text (None → simulated outage)."""

    def __init__(self, reply_text: str | None):
        self._cost_tracker = _StubCostTracker()
        self._reply_text = reply_text

    def _resolve_effective_provider(self, *, base_provider, base_tier, role):
        return base_provider, base_tier

    async def _provider_complete(self, *, provider_name, tier, system_prompt, messages,
                                 tools, max_tokens, timeout):
        if self._reply_text is None:
            return None  # provider 不可用（真 outage）
        return _StubResponse(self._reply_text)


def _interpret(reply_text: str | None):
    """跑真 _run_cloud_interpret，回 (parsed, cloud_stage)。 / drive real fn, return (parsed, stage)."""
    eng = _StubEngine(reply_text)
    parsed, _raw, _cost, _sysp, meta = asyncio.run(
        EXEC._run_cloud_interpret(eng, mode="diagnose_leak", context={"training_run_id": "r1"})
    )
    return parsed, meta.get("cloud_stage")


class TestStageClassificationHonestBoundary:
    def test_provider_none_yields_cloud_unavailable(self):
        """provider 回 None（真 outage）→ cloud_stage=cloud_unavailable，parsed=None。
        Provider returns None (true outage) → cloud_stage=cloud_unavailable."""
        parsed, stage = _interpret(None)
        assert parsed is None
        assert stage == "cloud_unavailable"

    def test_fenced_valid_reply_yields_ok(self):
        """有回覆且帶 ```json fence 可 parse → cloud_stage=ok，parsed=dict。
        Present + fenced parseable reply → cloud_stage=ok, parsed=dict.

        mutation-bite：若回退成「對原始文本直接 json.loads」（不剝 fence），此帶殼回覆會 parse
        失敗 → stage 變 parse_failed，本斷言 ok 會轉紅。故 fence-strip 回退會 bite。"""
        fenced = "Sure:\n```json\n" + json.dumps(_VALID_DIAGNOSE_OUTPUT) + "\n```\nDone."
        parsed, stage = _interpret(fenced)
        assert isinstance(parsed, dict)
        assert parsed == _VALID_DIAGNOSE_OUTPUT
        assert stage == "ok"

    def test_present_but_unparsable_yields_parse_failed_not_outage(self):
        """有回覆但無法 parse（散文）→ cloud_stage=parse_failed，**絕不** cloud_unavailable。
        Present-but-unparsable reply → parse_failed, NEVER cloud_unavailable (honest boundary)."""
        parsed, stage = _interpret("Sorry, I cannot produce structured output right now.")
        assert parsed is None
        assert stage == "parse_failed"
        assert stage != "cloud_unavailable"  # 誠實邊界：有回覆 ≠ outage

    def test_parse_failed_and_cloud_unavailable_are_distinct_labels(self):
        """兩個退化階段是**不同** enum 標籤（split stage：一個是格式問題、一個是可用性問題）。
        The two degraded stages are DISTINCT labels (parse vs availability)."""
        _, outage_stage = _interpret(None)
        _, unparsable_stage = _interpret("no json here at all")
        assert outage_stage == "cloud_unavailable"
        assert unparsable_stage == "parse_failed"
        assert outage_stage != unparsable_stage


if __name__ == "__main__":  # pragma: no cover — 允許不經 pytest 直跑（快速 smoke）
    sys.exit(pytest.main([__file__, "-q"]))
