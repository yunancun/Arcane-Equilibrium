"""
L2 Advisory Mesh — Phase 3a（ml_advisory diagnose_leak + interpret_result cascade）測試。
驗「意圖」非僅行為（CLAUDE Operating Style 9）。

覆蓋（對映 PA P3 設計 §C/§D/§G.2/§H/§L + brief F）：
  - 2 模式：diagnose_leak / interpret_result 各跑完整 cascade（contract → cloud → guard → sink）。
  - cascade（§D）：Ollama screen → cloud-L2（survivors only）→ 確定性 guard（M3 typing）→ sink。
      * cost only on survivors：screen reject ⇒ 零 cloud call（mutation 驗）。
      * M4 校準：無 benchmark / recall<0.85 → screen DISABLED（全進 gate + flag MIT）。
      * M3 typing：name_pattern_check 宣稱 leak-free PIT → guard reject ⇒ 不寫 sink。
      * LLM 永不驗 alpha：cascade 無 alpha gate；guard 只 typing/形檢（grep + 行為驗）。
  - dispatch reachability（§C）：dispatch_and_execute 活化 dormant 路徑（admitted+neutral+ml_advisory
    才接 executor）；disabled/deduped/tier/MANUAL/fail-safe 短路不呼 model。
  - coarse_subject DoS（E3 P3-flag）：server-derive 低基數 + TTL/maxsize eviction（有界不變式）。
  - sink（§A.1）：0 新執行權——寫 genuinely-inert 的 agent.lessons（無 applier 掃描），content 過
      secret redactor，context_id=l2_reply_id（D3 鏈），source='ml_advisory'（與 critic 分離）。
  - regime_caveat guard + bull-only labeling（§H / Alpha Evidence Governance）。

Mac-tested（mocked PG via conn_provider 注入 + fake engine；無真 DB / 無真 model）。
Linux E4 regression + E3 對抗 + MIT（M3/M4）owed。
"""

from __future__ import annotations

import asyncio
import ast
import inspect
import io
import json
import sys
import tokenize
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import l2_advisory_orchestrator as ORCH
from app import l2_capability_registry as REG
from app import l2_memory_recall_context as MRC
from app import l2_ml_advisory_executor as EXEC
from app import l2_out_of_bound_guard as GUARD
from app import l2_prompt_contract_registry as CONTRACTS
from app.learning_tier_gate import LearningTier
from ml_training.advisory_review_packet import stable_sha256_json, validate_advisory_review_packet


# ═══════════════════════════════════════════════════════════════════════════════
# 測試輔助：fake engine（provider_complete 可控）+ conn_provider（捕捉 sink INSERT）
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeResponse:
    def __init__(self, text: str, in_tok: int = 10, out_tok: int = 20):
        self.text = text
        self.input_tokens = in_tok
        self.output_tokens = out_tok


class _FakeConfig:
    default_provider = "anthropic"


class _FakeCostTracker:
    def __init__(self):
        self.recorded: list[tuple[int, int, str]] = []

    def get_config(self):
        return _FakeConfig()

    def record_claude_cost(self, session, in_tok, out_tok, model_tier):
        # 模擬真記帳：回確定性小額 cost（cost only on survivors 的驗證用）+ 記錄呼叫。
        self.recorded.append((in_tok, out_tok, model_tier))
        return 0.01

    def record_call(self, **kwargs):
        pass


class _FakeEngine:
    """注入式 fake engine：screen + cloud 兩次 _provider_complete 回可控回應。

    screen_text：第一次（Ollama screen，triage role）回應。cloud_text：第二次（cloud-L2）回應。
    若任一設 None → _provider_complete 回 None（模擬 provider 不可用）。
    """

    def __init__(self, *, screen_text: str | None = '{"verdict":"pass"}', cloud_text: str | None = None):
        self._cost_tracker = _FakeCostTracker()
        self._screen_text = screen_text
        self._cloud_text = cloud_text
        self.calls: list[dict[str, Any]] = []

    def _resolve_effective_provider(self, *, base_provider, base_tier, role):
        return base_provider, base_tier

    async def _provider_complete(self, *, provider_name, tier, system_prompt, messages, tools, max_tokens, timeout):
        self.calls.append({
            "role_tier": tier,
            "system_prompt": system_prompt,
            "messages": messages,
            "max_tokens": max_tokens,
        })
        # 用 max_tokens 區分 screen（小）vs cloud（大）；screen=_SCREEN_MAX_TOKENS。
        is_screen = max_tokens <= EXEC._SCREEN_MAX_TOKENS
        text = self._screen_text if is_screen else self._cloud_text
        if text is None:
            return None
        return _FakeResponse(text)


class _CapturingConn:
    """注入式 conn（contextmanager）：捕捉 sink INSERT 的 SQL + params（不打真 DB）。"""

    def __init__(self, store: list[dict[str, Any]]):
        self._store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self._store.append({"sql": sql, "params": params})

    def commit(self):
        pass

    def rollback(self):
        pass


def _conn_provider_factory(store: list[dict[str, Any]]):
    """回一個 contextmanager-style conn_provider（每次回捕捉 conn）。"""
    def _provider():
        return _CapturingConn(store)
    return _provider


def _enabled_calibration():
    """screen ENABLED 的 calibration（recall≥floor，有 benchmark）。"""
    return EXEC.OllamaScreenCalibration(
        enabled=True, recall=0.92, threshold=0.85, benchmark_version="v1_test", reason="calibrated"
    )


def _diagnose_context():
    return {
        "training_run_id": "run-123",
        "metrics": {"auc": 0.55, "sharpe": 0.3, "pbo": 0.4, "dsr": 0.1, "cost_edge_ratio": 1.2},
        "leakage_check_findings": ["future_return in feature set"],
        "drift_signals": ["feature_importance shift > 0.3"],
    }


def _interpret_context(bull_only: bool = False):
    return {
        "training_run_id": "run-456",
        "metrics": {"auc": 0.6, "sharpe": 0.5, "bull_only": bull_only},
        "feature_importance": [{"name": "adx_1h", "gain": 0.4}],
        "regime_label": "bull" if bull_only else "mixed",
    }


# 合法 diagnose 輸出（M3：source_class=name_pattern_check，不宣稱 leak-free）。
_VALID_DIAGNOSE_OUTPUT = {
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

# 合法 interpret 輸出（bull-only 帶 regime_caveat）。
_VALID_INTERPRET_OUTPUT = {
    "mode": "interpret_result",
    "result_interpretation": {
        "reading": "signal present in bull regime",
        "regime_caveat": "bull-only; regime-bet/learning-only, not promotion proof",
        "confidence": "low",
    },
}


def _run(coro):
    return asyncio.run(coro)


def test_attach_advisory_review_packet_discards_model_supplied_packet():
    """model/advisory 自帶 packet 不可被保留，也不可進 input hash。"""
    malicious_packet = {
        "schema_version": "advisory_review_packet_v1",
        "active": True,
        "execution_authority": "granted",
        "order_mutation_allowed": True,
    }
    advisory_output = {
        "mode": "diagnose_leak",
        "leak_drift_diagnosis": _VALID_DIAGNOSE_OUTPUT["leak_drift_diagnosis"],
        "advisory_review_packet": malicious_packet,
    }

    attached, packet = EXEC._attach_advisory_review_packet(
        capability_id="ml_advisory.diagnose_leak",
        mode="diagnose_leak",
        advisory_output=advisory_output,
        input_context={"training_run_id": "run-123"},
        l2_reply_id="l2r:local",
        cost_usd=0.03,
    )

    assert attached["advisory_review_packet"] == packet
    assert attached["advisory_review_packet"] is not malicious_packet
    assert validate_advisory_review_packet(packet)
    expected_output_hash = stable_sha256_json({
        "mode": "diagnose_leak",
        "leak_drift_diagnosis": _VALID_DIAGNOSE_OUTPUT["leak_drift_diagnosis"],
    })
    assert packet["input_hashes"]["advisory_output"] == expected_output_hash
    assert packet["execution_authority"] == "not_granted"


def _code_only(path: Path) -> str:
    """剝除註解 + docstring，只留真碼 token（grep 鐵律用，非散文）。"""
    src = path.read_text(encoding="utf-8")
    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return src
    return " ".join(out)


_EXEC_CODE = _code_only(PROJECT_ROOT / "app" / "l2_ml_advisory_executor.py")


@pytest.fixture(autouse=True)
def _mock_ledger(monkeypatch):
    """所有 cascade 測試：D3 writer 注入 mock（record_l2_call / record_gate_seam 不打真 DB）。"""
    fake = MagicMock()
    fake.record_l2_call.return_value = {"ok": True}
    fake.record_gate_seam.return_value = {"ok": True}
    monkeypatch.setattr(EXEC, "_get_l2_ledger_writer", lambda: fake)
    return fake


# ═══════════════════════════════════════════════════════════════════════════════
# 2 模式 — diagnose_leak / interpret_result 完整 cascade
# ═══════════════════════════════════════════════════════════════════════════════


class TestTwoModesCascade:
    def test_diagnose_leak_full_cascade_writes_sink(self):
        """diagnose_leak：screen pass → cloud → guard pass → sink（applied=false）。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="ml_advisory_diagnose.v1", schema_ver="ml_advisory_schema.v1",
            calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.ok is True
        assert res.stage == "sink_written"
        assert res.cloud_called is True
        assert res.guard_verdict == "pass"
        assert res.sink_written is True
        assert len(store) == 1  # 恰一筆 sink INSERT
        assert validate_advisory_review_packet(res.advisory_review_packet)
        assert res.advisory_review_packet["ledger_ref"] == res.l2_reply_id
        assert res.advisory_review_packet["cost_ref"] == res.l2_reply_id

    def test_interpret_result_full_cascade_writes_sink(self):
        """interpret_result：bull-only 帶 regime_caveat → guard pass → sink。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_INTERPRET_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.interpret_result", mode="interpret_result",
            context=_interpret_context(bull_only=True), engine=eng,
            contract_ver="ml_advisory_interpret.v1", schema_ver="ml_advisory_schema.v1",
            calibration=_enabled_calibration(), bull_only=True,
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.ok is True
        assert res.guard_verdict == "pass"
        assert res.sink_written is True

    def test_unknown_mode_failclosed_no_model_call(self):
        """未知 mode → fail-closed reject，零 model 呼叫。

        P3b（2026-06-09）把 hypothesize 升為合法模式（alpha-bearing，走 §G.2 cascade）；故此處
        改用「真未知」mode 驗 fail-closed 路徑仍在（hypothesize 的 cascade 另有專屬測試）。
        """
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.bogus", mode="bogus_mode",
            context={}, engine=eng,
            contract_ver="x", schema_ver="y", calibration=_enabled_calibration(),
        ))
        assert res.ok is False
        assert res.stage == "unknown_mode_rejected"
        assert eng.calls == []  # 零 model 呼叫（screen + cloud 都沒跑）

    def test_d3_ledger_written_with_contract_versions(self, _mock_ledger):
        """每 cascade call → D3 ledger（contract_ver/schema_ver/guard_verdict/fact_inf_assm）。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="ml_advisory_diagnose.v1", schema_ver="ml_advisory_schema.v1",
            calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert _mock_ledger.record_l2_call.called
        kwargs = _mock_ledger.record_l2_call.call_args.kwargs
        assert kwargs["contract_ver"] == "ml_advisory_diagnose.v1"
        assert kwargs["schema_ver"] == "ml_advisory_schema.v1"
        assert kwargs["guard_verdict"] == "pass"
        packet = kwargs["parsed_output"]["advisory_review_packet"]
        assert validate_advisory_review_packet(packet)
        assert packet["capability_id"] == "ml_advisory.diagnose_leak"
        assert packet["budget_ref"] == "DOC-08"
        # fact_inf_assm 帶 mode + evidence kinds（事實/推論/假設分離，root principle 10）。
        assert kwargs["fact_inf_assm"]["mode"] == "diagnose_leak"
        assert "leak" in kwargs["fact_inf_assm"]["evidence_kinds"]


class TestB3MemoryRecallWiring:
    def test_shadow_recall_is_ledger_only_not_model_prompt(self, monkeypatch, _mock_ledger):
        """OPENCLAW_L2_MEMORY_RECALL=shadow：算 bundle，但只入 D3 input_context，不改 prompt。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        recall = MRC.L2MemoryRecallContext(
            mode="shadow",
            attempted=True,
            record_ids=("mem:r1", "mem:i1"),
            total_chars=44,
            degraded_level="fts",
            stable_block="- [rule] should not enter system prompt",
            recent_block="- [incident] should not enter user prompt",
        )

        async def _fake_build(**_kwargs):
            return recall

        monkeypatch.setattr(EXEC, "_build_l2_memory_recall", _fake_build)
        _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))

        cloud_call = [c for c in eng.calls if c["max_tokens"] == EXEC._CLOUD_MAX_TOKENS][0]
        assert "should not enter system prompt" not in cloud_call["system_prompt"]
        assert "should not enter user prompt" not in cloud_call["messages"][0]["content"]
        payload = _mock_ledger.record_l2_call.call_args.kwargs["input_context"][
            "memory_recall_shadow"
        ]
        assert payload == {
            "mode": "shadow",
            "record_ids": ["mem:r1", "mem:i1"],
            "total_chars": 44,
            "degraded_level": "fts",
        }

    def test_active_recall_injects_cloud_prompt_and_audits_ids(self, monkeypatch, _mock_ledger):
        """OPENCLAW_L2_MEMORY_RECALL=1：stable 進 system，recent 進 user，ledger 留 ids。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        recall = MRC.L2MemoryRecallContext(
            mode="1",
            attempted=True,
            record_ids=("mem:r2",),
            total_chars=33,
            degraded_level="vector",
            stable_block="- [rule] stable B3 rule",
            recent_block="- [incident] recent B3 incident",
        )

        async def _fake_build(**_kwargs):
            return recall

        monkeypatch.setattr(EXEC, "_build_l2_memory_recall", _fake_build)
        _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))

        cloud_call = [c for c in eng.calls if c["max_tokens"] == EXEC._CLOUD_MAX_TOKENS][0]
        assert "stable B3 rule" in cloud_call["system_prompt"]
        assert "recent B3 incident" in cloud_call["messages"][0]["content"]
        kwargs = _mock_ledger.record_l2_call.call_args.kwargs
        assert "stable B3 rule" in kwargs["system_prompt"]
        assert kwargs["input_context"]["memory_recall_shadow"]["record_ids"] == ["mem:r2"]


# ═══════════════════════════════════════════════════════════════════════════════
# cascade §D — Ollama screen → cloud（survivors only）→ guard → sink
# ═══════════════════════════════════════════════════════════════════════════════


class TestCascadeOllamaScreen:
    def test_screen_reject_short_circuits_no_cloud_call(self):
        """cost only on survivors：screen "skip" → 零 cloud call（短路）；不寫 sink。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(screen_text='{"verdict":"skip","reason":"empty run"}',
                          cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.stage == "screen_rejected"
        assert res.cloud_called is False
        assert res.sink_written is False
        # 只跑了 screen（1 call），沒跑 cloud（cost only on survivors）。
        assert len(eng.calls) == 1
        assert eng.calls[0]["max_tokens"] == EXEC._SCREEN_MAX_TOKENS
        assert store == []  # 零 sink 寫入

    def test_screen_pass_then_cloud_called(self):
        """screen "pass" → cloud 被呼（2 calls：screen + cloud）。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(screen_text='{"verdict":"pass"}', cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.cloud_called is True
        assert len(eng.calls) == 2

    def test_cloud_unavailable_fail_soft_no_sink(self, _mock_ledger):
        """cloud 回 None（provider 不可用）→ fail-soft，不寫 sink（D3 記 inactive error packet）。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(screen_text='{"verdict":"pass"}', cloud_text=None)
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.ok is False
        assert res.stage == "cloud_unavailable_or_unparsable"
        assert store == []
        kwargs = _mock_ledger.record_l2_call.call_args.kwargs
        parsed_output = kwargs["parsed_output"]
        assert parsed_output["mode"] == "diagnose_leak"
        assert parsed_output["stage"] == "cloud_unavailable_or_unparsable"
        assert parsed_output["error"] == "cloud_no_output_or_unparsable"
        assert parsed_output["no_output"] is True
        assert parsed_output["advisory_success"] is False
        assert parsed_output["l2_reply_id"] == res.l2_reply_id
        assert parsed_output["cost_usd"] == res.cost_usd
        assert parsed_output["advisory_review_packet"] == res.advisory_review_packet
        assert validate_advisory_review_packet(parsed_output["advisory_review_packet"])
        assert parsed_output["advisory_review_packet"]["ledger_ref"] == res.l2_reply_id

    def test_mutation_bite_cloud_only_on_screen_survivors(self):
        """mutation 驗：cloud 只在 screen pass 後跑。

        構造 screen=skip：正確實作（survivors-only）→ cloud_called=False。若回退成「screen 後
        無條件呼 cloud」→ cloud_called=True（紅）。此測斷言 False，故回退會 bite。
        """
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(screen_text='{"verdict":"skip"}', cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.cloud_called is False, "cloud 必只在 screen survivor 跑（cost only on survivors）"

    def test_cost_routes_through_record_claude_cost_for_doc08(self):
        """cost 經 record_claude_cost 記帳（計入 DOC-08 daily counter；admission budget 閘可見）。

        為什麼重要：ml_advisory cloud/screen 花費若不計入全域 daily counter，admission $2/day 硬閘
        看不到 ml_advisory 花費 = storm 防護漏洞。此測證 cloud-L2 step 真呼 record_claude_cost。
        """
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        # screen + cloud 各記一次 record_claude_cost（計入 DOC-08）。
        assert len(eng._cost_tracker.recorded) == 2
        assert res.cost_usd > 0  # 真計到 cost（非永遠 0）


# ═══════════════════════════════════════════════════════════════════════════════
# M4 — Ollama screen 校準機制（recall≥0.85=loose；<floor / 無 benchmark → DISABLE screen）
# ═══════════════════════════════════════════════════════════════════════════════


class TestM4ScreenCalibration:
    def test_no_benchmark_artifact_disables_screen(self, tmp_path):
        """無 benchmark artifact → screen DISABLED（fail-closed：全進 gate + flag MIT）。"""
        calib = EXEC.load_ollama_screen_calibration(artifact_path=tmp_path / "absent.json")
        assert calib.enabled is False
        assert calib.benchmark_version == "absent"
        assert "flag_mit" in calib.reason

    def test_recall_below_floor_disables_screen(self, tmp_path):
        """recall < 0.85 floor → screen DISABLED（design line 1271；flag MIT）。"""
        art = tmp_path / "calib.json"
        art.write_text(json.dumps({"benchmark_version": "v2", "recall": 0.70}), encoding="utf-8")
        calib = EXEC.load_ollama_screen_calibration(artifact_path=art)
        assert calib.enabled is False
        assert calib.recall == 0.70
        assert "below_floor" in calib.reason

    def test_recall_at_or_above_floor_enables_screen(self, tmp_path):
        """recall ≥ 0.85 且有 benchmark → screen ENABLED（loose 操作點）。"""
        art = tmp_path / "calib.json"
        art.write_text(json.dumps({"benchmark_version": "v3", "recall": 0.88}), encoding="utf-8")
        calib = EXEC.load_ollama_screen_calibration(artifact_path=art)
        assert calib.enabled is True
        assert calib.recall == 0.88

    def test_malformed_artifact_disables_screen(self, tmp_path):
        """壞 artifact → screen DISABLED（不啟用未驗 screen；fail-closed）。"""
        art = tmp_path / "bad.json"
        art.write_text("{not valid json", encoding="utf-8")
        calib = EXEC.load_ollama_screen_calibration(artifact_path=art)
        assert calib.enabled is False
        assert calib.benchmark_version == "malformed"

    def test_screen_disabled_routes_everything_to_gate_flag_mit(self, _mock_ledger):
        """screen DISABLED：cascade 全進 gate（不跑 screen call）+ gate-seam 記 disabled（flag MIT）。"""
        store: list[dict[str, Any]] = []
        disabled = EXEC.OllamaScreenCalibration(
            enabled=False, recall=None, threshold=0.85, benchmark_version="absent",
            reason="no_benchmark_artifact_screen_disabled_flag_mit",
        )
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=disabled,
            sink_conn_provider=_conn_provider_factory(store),
        ))
        # screen 停用：未跑 screen call（直接 cloud）；全進 gate。
        assert res.screen_disabled is True
        assert res.screen_passed is True  # 全進 gate（不丟 alpha）
        assert res.cloud_called is True
        assert len(eng.calls) == 1  # 只有 cloud call，無 screen call
        # gate-seam 記 ollama_screen "disabled"（applied_as=screen_disabled_flag_mit）。
        seam_calls = [c for c in _mock_ledger.record_gate_seam.call_args_list
                      if c.kwargs.get("gate_id") == "ollama_screen"]
        assert seam_calls, "screen disabled 須落 ollama_screen gate-seam"
        assert seam_calls[0].kwargs["applied_as"] == "screen_disabled_flag_mit"

    def test_mutation_bite_low_recall_must_disable(self, tmp_path):
        """mutation 驗：recall<floor 必 disable。若回退成「無條件 enable」→ 此測紅。"""
        art = tmp_path / "calib.json"
        art.write_text(json.dumps({"benchmark_version": "v", "recall": 0.50}), encoding="utf-8")
        calib = EXEC.load_ollama_screen_calibration(artifact_path=art, recall_floor=0.85)
        assert calib.enabled is False, "recall 0.50 < 0.85 必 disable screen（M4）"


# ═══════════════════════════════════════════════════════════════════════════════
# M3 — source_class typing（diagnose）；guard 是 P3a 主 gate（無 alpha math gate）
# ═══════════════════════════════════════════════════════════════════════════════


class TestM3LeakTyping:
    def test_leakfree_claim_via_name_pattern_check_rejected(self):
        """M3 鐵律：name_pattern_check 宣稱 leak-free PIT → guard reject ⇒ 不寫 sink。"""
        store: list[dict[str, Any]] = []
        bad_output = {
            "mode": "diagnose_leak",
            "leak_drift_diagnosis": {
                "suspected_cause": "none",
                "evidence": [
                    # 用 name_pattern_check 卻宣稱 leak_free=true → M3 typing reject。
                    {"claim": "no leak", "kind": "leak", "source_ref": "leakage_check",
                     "source_class": "name_pattern_check", "leak_free": True}
                ],
                "recommended_check": "none",
            },
        }
        eng = _FakeEngine(cloud_text=json.dumps(bad_output))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.guard_verdict == "reject"
        assert res.stage == "guard_rejected"
        assert res.sink_written is False
        assert store == []  # guard reject ⇒ logged-and-dropped，不寫 sink

    def test_invalid_source_class_rejected(self):
        """source_class ∉ 合法集合 → guard reject（M3 typing 強制）。"""
        store: list[dict[str, Any]] = []
        bad_output = {
            "mode": "diagnose_leak",
            "leak_drift_diagnosis": {
                "suspected_cause": "x", "recommended_check": "y",
                "evidence": [{"claim": "c", "kind": "leak", "source_ref": "r",
                              "source_class": "made_up_class"}],
            },
        }
        eng = _FakeEngine(cloud_text=json.dumps(bad_output))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.guard_verdict == "reject"
        assert store == []

    def test_name_pattern_check_without_leakfree_claim_passes(self):
        """name_pattern_check 不宣稱 leak-free（只報 finding）→ guard pass（合法弱證據）。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.guard_verdict == "pass"
        assert res.sink_written is True

    def test_leakfree_source_classes_exclude_name_pattern_check(self):
        """M3 常數：leak-free 集合不含 name_pattern_check（只 shift1_compliance/is_oos_gap 可）。"""
        assert "name_pattern_check" not in CONTRACTS.ML_ADVISORY_LEAKFREE_SOURCE_CLASSES
        assert CONTRACTS.ML_ADVISORY_LEAKFREE_SOURCE_CLASSES == frozenset(
            {"shift1_compliance", "is_oos_gap"}
        )


# ═══════════════════════════════════════════════════════════════════════════════
# regime_caveat guard + bull-only labeling（§H / Alpha Evidence Governance）
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegimeCaveatGuard:
    def test_bull_only_promotion_ready_missing_caveat_rejected(self):
        """interpret 宣稱 promotion_ready 且 bull-only 卻無 regime_caveat → guard reject。"""
        store: list[dict[str, Any]] = []
        bad_output = {
            "mode": "interpret_result",
            "result_interpretation": {
                "reading": "strong signal", "promotion_ready": True,
                "regime_caveat": "",  # 缺 caveat
                "confidence": "high",
            },
        }
        eng = _FakeEngine(cloud_text=json.dumps(bad_output))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.interpret_result", mode="interpret_result",
            context=_interpret_context(bull_only=True), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            bull_only=True, sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.guard_verdict == "reject"
        assert res.sink_written is False

    def test_bull_only_with_caveat_passes(self):
        """interpret bull-only 帶非空 regime_caveat → guard pass（合規標 regime-bet/learning-only）。"""
        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_INTERPRET_OUTPUT))
        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.interpret_result", mode="interpret_result",
            context=_interpret_context(bull_only=True), engine=eng,
            contract_ver="cv", schema_ver="sv", calibration=_enabled_calibration(),
            bull_only=True, sink_conn_provider=_conn_provider_factory(store),
        ))
        assert res.guard_verdict == "pass"
        assert res.sink_written is True

    def test_guard_unit_bull_only_missing_caveat_direct(self):
        """guard 單元直驗（不經 cascade）：bull-only + promotion_ready + 無 caveat → reject。"""
        out = {
            "mode": "interpret_result",
            "result_interpretation": {"reading": "x", "promotion_ready": True, "confidence": "high"},
        }
        r = GUARD.run_guard(out, guard_ref="ml_advisory.guard.v1", context={"bull_only": True})
        assert r.verdict == "reject"
        assert any("regime_caveat" in k for k in r.kinds_hit)


# ═══════════════════════════════════════════════════════════════════════════════
# sink §A.1 — 0 新執行權（結構性：寫 genuinely-inert 的 agent.lessons，無 applier 掃描）
# ═══════════════════════════════════════════════════════════════════════════════
#
# operator 拍板把 sink 從 mlde_shadow_recommendations 改為 agent.lessons：後者的 source='ml_shadow'
# + recommendation_type='regret_summary' 正是 active 的 mlde_demo_applier 掃描去 mutate demo
# RiskConfig 的 namespace（若 MIN_CONFIDENCE=0，P3a 中性診斷被抓去改配置）。agent.lessons 無任何
# applier 掃描它去執行，故「0 新執行權」在此 sink 結構性成立（非靠 applied=false 旗標）。


class TestAdvisorySinkZeroExecAuthority:
    def test_sink_writes_to_agent_lessons_not_applier_scanned_table(self):
        """sink 寫進 genuinely-inert 的 agent.lessons，NOT 任何 applier-掃描表
        （mlde_shadow_recommendations 等 applier namespace 一律不出現在 SQL）。"""
        store: list[dict[str, Any]] = []
        res = EXEC.write_ml_advisory_advisory_sink(
            engine_mode="demo", mode="diagnose_leak", parsed_output=_VALID_DIAGNOSE_OUTPUT,
            l2_reply_id="l2r:abc", conn_provider=_conn_provider_factory(store),
        )
        assert res["ok"] is True
        assert len(store) == 1  # 恰一筆 sink INSERT
        sql = store[0]["sql"]
        # 寫進 agent.lessons（genuinely inert）。
        assert "INSERT INTO agent.lessons" in sql
        # mutation-bite：永不寫進 applier-掃描的交易推薦表（0 新執行權結構性）。
        assert "mlde_shadow_recommendations" not in sql
        assert "decision_lease" not in sql.lower()
        assert "applied" not in sql.lower()  # agent.lessons 無 applied 欄（不再有旗標語義）

    def test_sink_tags_source_ml_advisory_distinct_from_critic(self):
        """sink 用 source='ml_advisory'（與 critic lessons 的 'l2_session' 分離 namespace，避免
        污染 critic 的 pg_trgm 檢索池語義）+ lesson_type=mode。"""
        store: list[dict[str, Any]] = []
        EXEC.write_ml_advisory_advisory_sink(
            engine_mode="demo", mode="diagnose_leak", parsed_output=_VALID_DIAGNOSE_OUTPUT,
            l2_reply_id="l2r:abc", conn_provider=_conn_provider_factory(store),
        )
        params = store[0]["params"]
        # params 順序：symbol, lesson_type, content, session_trigger, context_id, source
        assert params[1] == "diagnose_leak"  # lesson_type=mode（可區辨）
        assert params[5] == "ml_advisory"  # source discriminator（與 critic 'l2_session' 分離）
        assert params[5] != "l2_session"  # mutation-bite：誤用 critic namespace → 紅

    def test_sink_context_id_is_l2_reply_id_for_d3_provenance(self):
        """sink context_id = l2_reply_id（D3 provenance 鏈；lesson 可逆溯回 agent.l2_calls）。"""
        store: list[dict[str, Any]] = []
        EXEC.write_ml_advisory_advisory_sink(
            engine_mode="demo", mode="interpret_result", parsed_output=_VALID_INTERPRET_OUTPUT,
            l2_reply_id="l2r:xyz", conn_provider=_conn_provider_factory(store),
        )
        params = store[0]["params"]
        assert params[4] == "l2r:xyz"  # context_id = l2_reply_id（D3 鏈）

    def test_sink_session_trigger_is_threaded_not_hardcoded(self):
        """sink session_trigger = 傳入的 trigger（真實觸發源，與 D3 ledger 一致；非硬編）。"""
        store: list[dict[str, Any]] = []
        EXEC.write_ml_advisory_advisory_sink(
            engine_mode="demo", mode="diagnose_leak", parsed_output=_VALID_DIAGNOSE_OUTPUT,
            l2_reply_id="l2r:abc", trigger="ml:custom_trigger",
            conn_provider=_conn_provider_factory(store),
        )
        params = store[0]["params"]
        assert params[3] == "ml:custom_trigger"  # session_trigger 用傳入值（非硬編 default）

    def test_sink_content_passes_through_redactor(self, monkeypatch):
        """mutation-bite：sink content 必過 l2_secret_redactor.redact()（無未消毒文本進 durable
        store）。注入 spy redactor，斷言它被本 sink 呼叫且寫入的是消毒後文本。"""
        store: list[dict[str, Any]] = []
        seen: dict[str, Any] = {}

        class _SpyResult:
            text = "[[REDACTED-SINK-CONTENT]]"

        def _spy_redact(text):
            seen["called_with"] = text
            return _SpyResult()

        # spy 掛在 executor import 的 redactor 別名上（_redactor.redact）。
        monkeypatch.setattr(EXEC._redactor, "redact", _spy_redact)
        EXEC.write_ml_advisory_advisory_sink(
            engine_mode="demo", mode="diagnose_leak", parsed_output=_VALID_DIAGNOSE_OUTPUT,
            l2_reply_id="l2r:abc", conn_provider=_conn_provider_factory(store),
        )
        # redactor 真被呼叫（原始 content 嵌 l2_reply_id + parsed）。
        assert "l2r:abc" in seen["called_with"]
        assert "ml_advisory_mode" in seen["called_with"]
        # 寫入 DB 的是消毒後文本（非原始）——若漏 redactor，content 會是原始 JSON（mutation 紅）。
        assert store[0]["params"][2] == "[[REDACTED-SINK-CONTENT]]"

    def test_sink_content_reconstructable_asserts_no_alpha(self):
        """sink content（未掛 spy 時）嵌 asserts_no_alpha + mode + l2_reply_id（reconstructable，
        可逆溯 D3）。content 是真消毒後字串（含上述標記，非被遮）。"""
        store: list[dict[str, Any]] = []
        EXEC.write_ml_advisory_advisory_sink(
            engine_mode="demo", mode="interpret_result", parsed_output=_VALID_INTERPRET_OUTPUT,
            l2_reply_id="l2r:xyz", strategy_name="bb_breakout",
            conn_provider=_conn_provider_factory(store),
        )
        content = store[0]["params"][2]
        # content 形如 "ml_advisory:interpret_result: {<json>}"，真隨機 secret 才被遮，這些標記留存。
        assert "ml_advisory:interpret_result" in content
        assert "asserts_no_alpha" in content
        assert "advisory_review_packet" in content
        assert "not_granted" in content
        assert "l2r:xyz" in content
        assert "bb_breakout" in content  # strategy_name 嵌 content（reconstructable）

    def test_sink_symbol_placeholder_when_none(self):
        """symbol 為 V133 NOT NULL：候選無 symbol → 用佔位 'ml_advisory'（不阻斷落庫）。"""
        store: list[dict[str, Any]] = []
        EXEC.write_ml_advisory_advisory_sink(
            engine_mode="demo", mode="diagnose_leak", parsed_output=_VALID_DIAGNOSE_OUTPUT,
            l2_reply_id="l2r:abc", symbol=None, conn_provider=_conn_provider_factory(store),
        )
        assert store[0]["params"][0] == "ml_advisory"  # symbol 佔位（NOT NULL 不違反）

    def test_sink_db_unavailable_fail_soft(self):
        """DB 不可用（conn=None）→ ok=False 但不 raise（fail-soft）。"""
        def _none_provider():
            class _C:
                def __enter__(self): return None
                def __exit__(self, *a): return False
            return _C()
        res = EXEC.write_ml_advisory_advisory_sink(
            engine_mode="demo", mode="diagnose_leak", parsed_output=_VALID_DIAGNOSE_OUTPUT,
            l2_reply_id="l2r:abc", conn_provider=_none_provider,
        )
        assert res["ok"] is False
        assert "db_unavailable" in res["errors"]

    def test_executor_source_zero_order_lease_promote(self):
        """grep 鐵律：executor 真碼 0 個 order/lease/promote/live-config 引用（剝註解後）。"""
        for forbidden in (
            "IntentProcessor", "submit_intent", "place_order", "acquire_lease",
            "promote_tier", "live_execution_allowed", "OPENCLAW_ALLOW_MAINNET",
            "execution_authority", "system_mode",
        ):
            assert forbidden not in _EXEC_CODE, f"executor 真碼不應含 {forbidden}（0 新執行權）"

    def test_executor_sink_targets_inert_agent_lessons_only(self):
        """grep 鐵律：executor 只寫 agent.lessons（genuinely inert），不出現 applier-掃描的
        mlde_shadow_recommendations INSERT（0 新執行權結構性成立）。

        為什麼正面查 raw source 而非 _EXEC_CODE：_code_only 剝掉 STRING token，SQL 字面
        'INSERT INTO agent.lessons' 在三引號字串內會被剝除（_EXEC_CODE 看不到）；故正面斷言查
        raw source。負面斷言（applier 表 identifier 不存在）查 raw source 一樣有效（更嚴：連
        字串/註解都不得殘留 applier 表名的 INSERT 語意）。
        """
        raw = (PROJECT_ROOT / "app" / "l2_ml_advisory_executor.py").read_text(encoding="utf-8")
        assert "INSERT INTO agent.lessons" in raw  # 真寫 inert lesson store
        # 真碼不該有 mlde_shadow_recommendations 的 INSERT（會被 mlde_demo_applier mutate 配置）。
        assert "INSERT INTO learning.mlde_shadow_recommendations" not in raw, \
            "executor 不該 INSERT applier-掃描的 mlde_shadow_recommendations"
        # _EXEC_CODE（剝註解+字串後的真碼 token）亦不得殘留該 identifier（防靠字串拼接繞過）。
        assert "mlde_shadow_recommendations" not in _EXEC_CODE


# ═══════════════════════════════════════════════════════════════════════════════
# LLM 永不驗 alpha（鐵律）— cascade 無 alpha gate；guard 只 typing/形檢
# ═══════════════════════════════════════════════════════════════════════════════


class TestLlmNeverValidatesAlpha:
    def test_llm_invocation_functions_have_no_alpha_gate(self):
        """鐵律（P3b）：LLM-invocation 函數（screen/generate/cloud-interpret）真碼無 alpha-gate 引用。

        P3b 把 alpha 驗證集中到「確定性 math gate」（dsr_gate/pbo_gate/beta_neutral_check 是唯一
        alpha validator）。鐵律不是「executor 完全無 alpha gate」（math gate 須有），而是「LLM
        永不驗 alpha」——故 LLM-invocation 函數體內不得引用任何 alpha gate（驗 alpha 只在確定性
        math gate stage 函數，那些函數另有「0 LLM-invocation」測試把關）。
        """
        src = (PROJECT_ROOT / "app" / "l2_ml_advisory_executor.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        llm_fns = {"_run_ollama_screen", "_run_ollama_generate", "_run_cloud_interpret"}
        alpha_tokens = ("dsr_gate", "pbo_gate", "beta_neutral", "residual_alpha_gate",
                        "compute_dsr", "compute_pbo", "beta_neutral_check", "_run_math_gate")
        found = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in llm_fns:
                found = True
                body_src = ast.get_source_segment(src, node) or ""
                for tok in alpha_tokens:
                    assert tok not in body_src, \
                        f"LLM-invocation 函數 {node.name} 不得引用 alpha gate {tok}（LLM 永不驗 alpha）"
        assert found, "未找到任何 LLM-invocation 函數（測試前提失效）"

    def test_math_gate_stage_functions_have_no_llm_invocation(self):
        """鐵律（P3b）：確定性 math gate stage 函數真碼 0 LLM-invocation（CC/E2/MIT grep target）。

        math gate 是唯一 alpha validator，且必為「確定性」——stage 函數體內不得有任何 model 呼叫
        （_provider_complete / run_session / _run_ollama* / _run_cloud*），確保 alpha 驗證 100%
        由數學決定，0 LLM 介入。
        """
        src = (PROJECT_ROOT / "app" / "l2_ml_advisory_executor.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        gate_fns = {"_run_math_gate", "_run_dsr_stage", "_run_pbo_stage", "_run_b1_stage",
                    "_run_leak_stage", "_strictest_math_verdict"}
        llm_tokens = ("_provider_complete", "run_session", "_run_ollama_screen",
                      "_run_ollama_generate", "_run_cloud_interpret", "provider_client")
        found = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in gate_fns:
                found = True
                body_src = ast.get_source_segment(src, node) or ""
                for tok in llm_tokens:
                    assert tok not in body_src, \
                        f"math gate 函數 {node.name} 不得含 LLM-invocation {tok}（math gate 是確定性唯一 validator）"
        assert found, "未找到任何 math gate stage 函數（測試前提失效）"

    def test_guard_is_deterministic_no_model_call(self):
        """guard 確定性：ml_advisory guard 真碼無 model 呼叫（guard 抓形非驗 alpha）。"""
        guard_code = _code_only(PROJECT_ROOT / "app" / "l2_out_of_bound_guard.py")
        for forbidden in ("run_session", "_provider_complete", "LocalLLMClient"):
            assert forbidden not in guard_code

    def test_contract_constraints_assert_no_alpha(self):
        """兩模式 PromptContract constraints 明示「asserts NO alpha」+「LLM NEVER validates alpha」。"""
        for ref in ("ml_advisory.diagnose_leak.v1", "ml_advisory.interpret_result.v1"):
            pc = CONTRACTS.get_prompt_contract(ref)
            assert pc is not None
            joined = " ".join(pc.constraints).lower()
            assert "no alpha" in joined or "asserts no alpha" in joined
            assert "never validates alpha" in joined


# ═══════════════════════════════════════════════════════════════════════════════
# dispatch reachability §C — dispatch_and_execute 活化 dormant 路徑
# ═══════════════════════════════════════════════════════════════════════════════


def _make_ml_cap(capability_id="ml_advisory.diagnose_leak", **overrides):
    """建一個 enabled ml_advisory capability（neutral lane）。"""
    base = dict(
        capability_id=capability_id, enabled=True, min_tier="L1", model_tier="cloud_l2",
        lane="ml_backlog",  # → neutral
        prompt_contract_ref=f"{capability_id}.v1", output_schema_ref="ml_advisory.v1",
        out_of_bound_guard_ref="ml_advisory.guard.v1",
        trigger=REG.L2CapabilityTrigger(kind="event", spec="ml:training_complete", debounce_secs=0),
        budget=REG.L2CapabilityBudget(per_call_usd_cap=0.5, daily_usd_cap=0.5),
    )
    base.update(overrides)
    return REG.L2Capability(**base)


class _OrchFakeTracker:
    def check_daily_budget(self):
        return True, 2.0


def _orch_with_ml(cap, *, engine):
    reg = REG.L2CapabilityRegistry(capabilities={cap.capability_id: cap})
    return ORCH.L2AdvisoryOrchestrator(
        cost_tracker=_OrchFakeTracker(), registry_loader=lambda: reg,
        engine_provider=lambda: engine, current_tier=LearningTier.L1, posture="Standard",
    )


class TestDispatchReachability:
    def test_dispatch_and_execute_activates_cascade(self, monkeypatch):
        """dispatch_and_execute：admitted + neutral + ml_advisory → 真接 cascade（活化 dormant）。"""
        # orchestrator 的 ledger writer 注入 mock（admission gate-seam）。
        fake_writer = MagicMock()
        fake_writer.record_gate_seam.return_value = {"ok": True}
        fake_writer.record_l2_call.return_value = {"ok": True}
        monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
        monkeypatch.setattr(EXEC, "_get_l2_ledger_writer", lambda: fake_writer)

        store: list[dict[str, Any]] = []
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        cap = _make_ml_cap()
        o = _orch_with_ml(cap, engine=eng)

        # screen 校準：注入 enabled（避免讀真 artifact）——透過 monkeypatch executor loader。
        monkeypatch.setattr(EXEC, "load_ollama_screen_calibration", lambda **k: _enabled_calibration())
        # sink conn 注入捕捉 conn（避免真 DB）。
        monkeypatch.setattr(EXEC.db_pool, "get_pg_conn", _conn_provider_factory(store))

        r = _run(o.dispatch_and_execute(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), coarse_subject="BTCUSDT", now=1000.0,
        ))
        assert r.admitted is True
        assert r.routed_to == "neutral_sink"
        # cascade 真跑：cloud 被呼（2 calls：screen + cloud）+ sink 寫入。
        assert len(eng.calls) == 2
        assert r.guard_verdict == "pass"
        assert validate_advisory_review_packet(r.advisory_review_packet)
        assert any("sink_written=True" in n for n in r.notes)

    def test_disabled_capability_short_circuits_no_executor(self, monkeypatch):
        """capability disabled → 短路，零 model 呼叫（executor 不跑）。"""
        fake_writer = MagicMock()
        fake_writer.record_gate_seam.return_value = {"ok": True}
        monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        cap = _make_ml_cap(enabled=False)
        o = _orch_with_ml(cap, engine=eng)
        r = _run(o.dispatch_and_execute(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), now=1000.0,
        ))
        assert r.admitted is False
        assert r.admission_reason == "capability_disabled"
        assert r.advisory_review_packet is None
        assert eng.calls == []  # executor 未跑

    def test_deduped_trigger_short_circuits_no_executor(self, monkeypatch):
        """同 dedup_key 第二次 → deduped → 短路，executor 不跑（無第二次 model 呼叫）。"""
        fake_writer = MagicMock()
        fake_writer.record_gate_seam.return_value = {"ok": True}
        fake_writer.record_l2_call.return_value = {"ok": True}
        monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
        monkeypatch.setattr(EXEC, "_get_l2_ledger_writer", lambda: fake_writer)
        monkeypatch.setattr(EXEC, "load_ollama_screen_calibration", lambda **k: _enabled_calibration())
        store: list[dict[str, Any]] = []
        monkeypatch.setattr(EXEC.db_pool, "get_pg_conn", _conn_provider_factory(store))

        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        cap = _make_ml_cap()
        o = _orch_with_ml(cap, engine=eng)
        _run(o.dispatch_and_execute(capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
                                    context=_diagnose_context(), coarse_subject="BTC", now=1000.0))
        calls_after_first = len(eng.calls)
        # 第二次同 dedup_key（窗口內）→ deduped。
        r2 = _run(o.dispatch_and_execute(capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
                                         context=_diagnose_context(), coarse_subject="BTC", now=1000.5))
        assert r2.admitted is False
        assert r2.admission_reason == "trigger_deduped"
        assert len(eng.calls) == calls_after_first  # 無新增 model 呼叫

    def test_tier_locked_short_circuits_no_executor(self, monkeypatch):
        """min_tier 高於 current → tier_locked → executor 不跑。"""
        fake_writer = MagicMock()
        fake_writer.record_gate_seam.return_value = {"ok": True}
        monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        cap = _make_ml_cap(min_tier="L4")
        o = _orch_with_ml(cap, engine=eng)  # current_tier=L1
        r = _run(o.dispatch_and_execute(capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
                                        context=_diagnose_context(), now=1000.0))
        assert r.admission_reason == "tier_locked"
        assert eng.calls == []

    def test_non_ml_advisory_capability_not_routed_to_executor(self, monkeypatch):
        """非 ml_advisory capability（如 research）admitted neutral 但不接 ml_advisory executor。"""
        fake_writer = MagicMock()
        fake_writer.record_gate_seam.return_value = {"ok": True}
        monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        cap = _make_ml_cap(capability_id="some_other_cap", lane="research",
                           prompt_contract_ref="", out_of_bound_guard_ref="")
        o = _orch_with_ml(cap, engine=eng)
        r = _run(o.dispatch_and_execute(capability_id="some_other_cap", mode="diagnose_leak",
                                        context={}, now=1000.0))
        assert r.admitted is True
        assert r.routed_to == "neutral_sink"
        assert eng.calls == []  # 非 ml_advisory → 不接 executor

    def test_executor_records_per_cap_spend_to_orchestrator(self, monkeypatch):
        """executor 經 spend_recorder 累計 per-cap 花費（orchestrator per-cap 日上限可見）。"""
        fake_writer = MagicMock()
        fake_writer.record_gate_seam.return_value = {"ok": True}
        fake_writer.record_l2_call.return_value = {"ok": True}
        monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
        monkeypatch.setattr(EXEC, "_get_l2_ledger_writer", lambda: fake_writer)
        monkeypatch.setattr(EXEC, "load_ollama_screen_calibration", lambda **k: _enabled_calibration())
        store: list[dict[str, Any]] = []
        monkeypatch.setattr(EXEC.db_pool, "get_pg_conn", _conn_provider_factory(store))

        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        cap = _make_ml_cap()
        o = _orch_with_ml(cap, engine=eng)
        # 不傳 now（用 wall-clock）：executor 的 _record_spend 也用 wall-clock，兩者同 day_key。
        _run(o.dispatch_and_execute(capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
                                    context=_diagnose_context(), coarse_subject="BTC"))
        # cascade 累計了該 cap 花費（screen + cloud 各 0.01 → 0.02）；spend dict 非空 = 真記入。
        total_spent = sum(o._admission.cap_daily_spend.values())
        assert total_spent > 0, "executor 須經 record_capability_spend 累計 per-cap 花費"

    def test_engine_unavailable_fail_soft(self, monkeypatch):
        """engine 不可用 → cascade skipped（fail-soft，不 raise）；fail-safe SM 推進。"""
        fake_writer = MagicMock()
        fake_writer.record_gate_seam.return_value = {"ok": True}
        monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
        cap = _make_ml_cap()
        reg = REG.L2CapabilityRegistry(capabilities={cap.capability_id: cap})
        o = ORCH.L2AdvisoryOrchestrator(
            cost_tracker=_OrchFakeTracker(), registry_loader=lambda: reg,
            engine_provider=lambda: None,  # engine 不可用
            current_tier=LearningTier.L1, posture="Standard",
        )
        r = _run(o.dispatch_and_execute(capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
                                        context=_diagnose_context(), now=1000.0))
        assert any("engine 不可用" in n for n in r.notes)


# ═══════════════════════════════════════════════════════════════════════════════
# coarse_subject DoS（E3 P3-flag）— server-derive 低基數 + TTL/maxsize eviction
# ═══════════════════════════════════════════════════════════════════════════════


class TestCoarseSubjectDoSProtection:
    def test_derive_coarse_subject_low_cardinality(self):
        """server-derive：空→default；截斷超長；折非白名單字元；大小寫正規化。"""
        assert ORCH._derive_coarse_subject("") == "default"
        assert ORCH._derive_coarse_subject("BTCUSDT") == "BTCUSDT"
        assert ORCH._derive_coarse_subject("btcusdt") == "BTCUSDT"  # 大小寫正規化降基數
        # 超長 → 截斷 + :trunc 標記（防單一超長字串當 unique key）。
        long_s = "x" * 200
        out = ORCH._derive_coarse_subject(long_s)
        assert out.endswith(":trunc")
        assert len(out) <= ORCH._COARSE_SUBJECT_MAXLEN + len(":trunc")
        # 空白/控制字元折成 _（防無限變體）。
        assert " " not in ORCH._derive_coarse_subject("a b\tc")

    def test_high_cardinality_input_collapses_to_bounded_set(self):
        """高基數輸入（不同空白/大小寫變體）→ 折進有界桶（降基數）。"""
        # "BTC USDT" / "btc usdt" / "BTC\tUSDT" 因折疊+upper 應大量 collapse。
        variants = {
            ORCH._derive_coarse_subject(s)
            for s in ["BTC USDT", "btc usdt", "BTC\tUSDT", "Btc Usdt", "BTC_USDT"]
        }
        # 全折成 "BTC_USDT"（單一桶）。
        assert variants == {"BTC_USDT"}

    def test_ttl_evicts_stale_admission_keys(self):
        """TTL eviction：過 TTL 的 dedup key 在下次 admission 被清（有界）。"""
        cap = _make_ml_cap(trigger=REG.L2CapabilityTrigger(kind="event", spec="s", debounce_secs=0))
        reg = REG.L2CapabilityRegistry(capabilities={cap.capability_id: cap})
        o = ORCH.L2AdvisoryOrchestrator(cost_tracker=_OrchFakeTracker(), registry_loader=lambda: reg)
        # 在 t0 植入大量 key。
        t0 = 1000.0
        for i in range(50):
            o._admit(cap, coarse_subject=f"S{i}", ts=t0)
        assert len(o._admission.last_served_ts) == 50
        # 在 t0 + 2*TTL 跑一次 admission → 觸發 eviction，t0 的 key 全過 TTL 被清。
        later = t0 + 2 * ORCH._ADMISSION_KEY_TTL_SECS
        o._admit(cap, coarse_subject="NEW", ts=later)
        # 只剩 "NEW"（其餘 50 個過 TTL 被驅逐）。
        assert len(o._admission.last_served_ts) == 1

    def test_maxsize_evicts_oldest_keys(self, monkeypatch):
        """maxsize eviction：超硬上限 → 驅逐最舊（即便 derive 失效仍有界兜底）。"""
        # 把 maxsize 調小以便測試（避免造 4096 key）。
        monkeypatch.setattr(ORCH, "_ADMISSION_KEY_MAXSIZE", 10)
        cap = _make_ml_cap(trigger=REG.L2CapabilityTrigger(kind="event", spec="s", debounce_secs=0))
        reg = REG.L2CapabilityRegistry(capabilities={cap.capability_id: cap})
        o = ORCH.L2AdvisoryOrchestrator(cost_tracker=_OrchFakeTracker(), registry_loader=lambda: reg)
        # 餵 30 個不同 subject（同窗口內，ts 遞增）→ maxsize=10 兜底驅逐最舊。
        for i in range(30):
            o._admit(cap, coarse_subject=f"UNIQUE{i}", ts=1000.0 + i)
        # 有界：eviction 在 admit 開頭跑（add 前），故每 call 後最多 maxsize+1（remaining 個新 key）。
        # 關鍵不變式：遠小於 30（不隨輸入基數線性增長）= 防 memory DoS。
        assert len(o._admission.last_served_ts) <= ORCH._ADMISSION_KEY_MAXSIZE + 1

    def test_mutation_bite_unbounded_without_eviction(self):
        """mutation 驗：若無 eviction，高基數會無界增長（本測斷言 TTL 後有界）。

        構造：t0 植入 50 key，t0+2TTL 跑 1 次。正確（TTL evict）→ len==1；移除 eviction → len==51（紅）。
        """
        cap = _make_ml_cap(trigger=REG.L2CapabilityTrigger(kind="event", spec="s", debounce_secs=0))
        reg = REG.L2CapabilityRegistry(capabilities={cap.capability_id: cap})
        o = ORCH.L2AdvisoryOrchestrator(cost_tracker=_OrchFakeTracker(), registry_loader=lambda: reg)
        for i in range(50):
            o._admit(cap, coarse_subject=f"K{i}", ts=1000.0)
        o._admit(cap, coarse_subject="LATER", ts=1000.0 + 2 * ORCH._ADMISSION_KEY_TTL_SECS)
        assert len(o._admission.last_served_ts) == 1, "TTL eviction 必清過期 key（防 memory DoS）"

    def test_dedup_still_works_within_window_after_derive(self):
        """derive 後 dedup 仍正確：同原始 subject（derive 同桶）窗口內第二次 → deduped。"""
        cap = _make_ml_cap(trigger=REG.L2CapabilityTrigger(kind="event", spec="s", debounce_secs=0))
        reg = REG.L2CapabilityRegistry(capabilities={cap.capability_id: cap})
        o = ORCH.L2AdvisoryOrchestrator(cost_tracker=_OrchFakeTracker(), registry_loader=lambda: reg)
        d1 = o._admit(cap, coarse_subject="btc usdt", ts=1000.0)
        # "BTC USDT" derive 成同桶 "BTC_USDT" → 同 dedup_key → deduped。
        d2 = o._admit(cap, coarse_subject="BTC USDT", ts=1000.5)
        assert d1.admitted is True
        assert d2.admitted is False
        # AdmissionDecision 用 .reason（DispatchResult 才是 .admission_reason）。
        assert d2.reason == "trigger_deduped"


# ═══════════════════════════════════════════════════════════════════════════════
# D3 contract_ver provenance（re-E2 RETURN）— orchestrator → registry → ledger 端到端
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼這組是缺的覆蓋：既有 cascade 測試（TestTwoModesCascade 等）都直接 inject
# contract_ver="ml_advisory_diagnose.v1" 進 run_ml_advisory_cascade，**遮蔽** orchestrator
# dispatch_and_execute 自己解析並 thread 給 executor 的值。原 bug：dispatch_and_execute 用
# resolve_contract_versions(contract_ref=None) → branch-3 generic fallback l2_contract.v1/
# l2_schema.v1，與此 cap 真實送 cloud 的 per-mode 契約（ml_advisory_diagnose.v1/
# ml_advisory_schema.v1）分歧 → 每 D3 row 記錯 contract_ver/schema_ver（違 root principle 8）。
# 修法：dispatch_and_execute re-fetch cap 用 cap.prompt_contract_ref/output_schema_ref 解析
# （與 dispatch() :354-359 等價）。
#
# 這組測試的關鍵：**不** inject contract_ver 進 cascade（讓 orchestrator 真解析），對「真
# registry」斷言 D3-recorded contract_ver/schema_ver == get_prompt_contract(_MODE_CONTRACT_REF
# [mode]).contract_ver。mutation-bite：傳 None/錯 ref → 紅。


def _captured_ledger_kwargs(writer: MagicMock) -> dict[str, Any]:
    """從 mock D3 writer 抓最後一筆 record_l2_call 的 kwargs（= 真寫進 D3 row 的值）。"""
    assert writer.record_l2_call.called, "cascade 須落 D3 ledger（record_l2_call）"
    return writer.record_l2_call.call_args.kwargs


def _drive_dispatch_and_execute_real_registry(
    monkeypatch, *, capability_id: str, mode: str
) -> MagicMock:
    """驅動 dispatch_and_execute（admitted + enabled ml_advisory cap）對「真 registry」跑完整
    cascade，回 mock D3 writer（供斷言 record_l2_call 的 contract_ver/schema_ver）。

    刻意「不」mock resolve_contract_versions（讓 orchestrator 真解析 cap.prompt_contract_ref）；
    也「不」inject contract_ver 進 cascade（cascade 收 orchestrator thread 下來的值）。cap 用
    _make_ml_cap → prompt_contract_ref=f"{capability_id}.v1"=真 registry key（ml_advisory.
    diagnose_leak.v1 / ml_advisory.interpret_result.v1）、output_schema_ref="ml_advisory.v1"。
    """
    fake_writer = MagicMock()
    fake_writer.record_gate_seam.return_value = {"ok": True}
    fake_writer.record_l2_call.return_value = {"ok": True}
    monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
    monkeypatch.setattr(EXEC, "_get_l2_ledger_writer", lambda: fake_writer)
    monkeypatch.setattr(EXEC, "load_ollama_screen_calibration", lambda **k: _enabled_calibration())
    store: list[dict[str, Any]] = []
    monkeypatch.setattr(EXEC.db_pool, "get_pg_conn", _conn_provider_factory(store))

    valid = _VALID_DIAGNOSE_OUTPUT if mode == "diagnose_leak" else _VALID_INTERPRET_OUTPUT
    ctx = _diagnose_context() if mode == "diagnose_leak" else _interpret_context(bull_only=True)
    eng = _FakeEngine(cloud_text=json.dumps(valid))
    cap = _make_ml_cap(capability_id=capability_id)
    o = _orch_with_ml(cap, engine=eng)
    r = _run(o.dispatch_and_execute(
        capability_id=capability_id, mode=mode, context=ctx,
        coarse_subject="BTCUSDT", bull_only=(mode == "interpret_result"), now=1000.0,
    ))
    # 前提自驗：cascade 真跑到 sink（否則沒 D3 row 可斷言，等於空驗）。
    assert r.admitted is True
    assert r.routed_to == "neutral_sink"
    assert any("sink_written=True" in n for n in r.notes)
    return fake_writer


class TestD3ContractVerProvenance:
    def test_diagnose_d3_contract_ver_matches_real_registry(self, monkeypatch):
        """diagnose：dispatch_and_execute 寫進 D3 的 contract_ver/schema_ver == 真 registry 的
        per-mode 契約版本（ml_advisory_diagnose.v1 / ml_advisory_schema.v1），非 generic fallback。"""
        writer = _drive_dispatch_and_execute_real_registry(
            monkeypatch, capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak"
        )
        kwargs = _captured_ledger_kwargs(writer)
        # ground truth 取自真 registry（_MODE_CONTRACT_REF[mode] → get_prompt_contract.contract_ver）。
        pc = CONTRACTS.get_prompt_contract(EXEC._MODE_CONTRACT_REF["diagnose_leak"])
        assert pc is not None
        assert kwargs["contract_ver"] == pc.contract_ver == "ml_advisory_diagnose.v1"
        sch = CONTRACTS.get_output_schema(pc.output_schema_ref)
        assert sch is not None
        assert kwargs["schema_ver"] == sch.schema_ver == "ml_advisory_schema.v1"
        # 反向斷言：絕不是被 bug 記錯的 generic fallback（l2_contract.v1 / l2_schema.v1）。
        assert kwargs["contract_ver"] != CONTRACTS.L2_PROMPT_CONTRACT_VER
        assert kwargs["schema_ver"] != CONTRACTS.L2_OUTPUT_SCHEMA_VER

    def test_interpret_d3_contract_ver_matches_real_registry(self, monkeypatch):
        """interpret：D3 記 ml_advisory_interpret.v1 / ml_advisory_schema.v1（per-mode 契約，
        非 generic fallback）。證兩 branch（diagnose/interpret）皆收斂到各自真實契約。"""
        writer = _drive_dispatch_and_execute_real_registry(
            monkeypatch, capability_id="ml_advisory.interpret_result", mode="interpret_result"
        )
        kwargs = _captured_ledger_kwargs(writer)
        pc = CONTRACTS.get_prompt_contract(EXEC._MODE_CONTRACT_REF["interpret_result"])
        assert pc is not None
        assert kwargs["contract_ver"] == pc.contract_ver == "ml_advisory_interpret.v1"
        sch = CONTRACTS.get_output_schema(pc.output_schema_ref)
        assert sch is not None
        assert kwargs["schema_ver"] == sch.schema_ver == "ml_advisory_schema.v1"
        assert kwargs["contract_ver"] != CONTRACTS.L2_PROMPT_CONTRACT_VER

    def test_diagnose_and_interpret_record_distinct_contract_vers(self, monkeypatch):
        """兩 branch 收斂到「不同」的 per-mode contract_ver（diagnose≠interpret），證 orchestrator
        threading 真按 cap 解析（非常數 fallback 把兩者都記成同一個 l2_contract.v1）。"""
        w_diag = _drive_dispatch_and_execute_real_registry(
            monkeypatch, capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak"
        )
        cv_diag = _captured_ledger_kwargs(w_diag)["contract_ver"]
        w_interp = _drive_dispatch_and_execute_real_registry(
            monkeypatch, capability_id="ml_advisory.interpret_result", mode="interpret_result"
        )
        cv_interp = _captured_ledger_kwargs(w_interp)["contract_ver"]
        assert cv_diag == "ml_advisory_diagnose.v1"
        assert cv_interp == "ml_advisory_interpret.v1"
        assert cv_diag != cv_interp  # generic fallback 會把兩者都記成 l2_contract.v1（紅）

    def test_mutation_bite_orchestrator_never_resolves_via_none_for_ml_advisory(self, monkeypatch):
        """mutation-bite（直擊原 bug）：跑完整 dispatch_and_execute（含內部 dispatch() + executor
        路徑）時，對此 enabled ml_advisory cap 的「每一次」contract-version 解析都必帶 cap 的真實
        per-mode contract_ref，**絕無** contract_ref=None 的解析（=branch-3 generic fallback）。

        為什麼斷言「無 None」而非「有真 ref」：dispatch() 內部本就會用 cap 的真 ref 解析一次
        （:354-359），故「seen 中存在真 ref」對 buggy 變體也成立（無 bite）。原 bug 是
        dispatch_and_execute「額外」用 contract_ref=None 解析一次 → branch-3 generic fallback →
        D3 記錯。故唯一有 bite 的斷言是「沒有任何一次解析傳 None」：修正後兩次解析都帶真 ref；
        revert 成傳 None → 出現一次 None 解析（紅）。
        """
        seen_refs: list[Any] = []
        real_resolve = CONTRACTS.resolve_contract_versions

        def _spy_resolve(*, capability_id, contract_ref=None, schema_ref=None):
            seen_refs.append({"contract_ref": contract_ref, "schema_ref": schema_ref})
            return real_resolve(
                capability_id=capability_id, contract_ref=contract_ref, schema_ref=schema_ref
            )

        # spy 掛在 orchestrator import 的 registry 別名上（_contracts.resolve_contract_versions）。
        monkeypatch.setattr(ORCH._contracts, "resolve_contract_versions", _spy_resolve)

        fake_writer = MagicMock()
        fake_writer.record_gate_seam.return_value = {"ok": True}
        fake_writer.record_l2_call.return_value = {"ok": True}
        monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake_writer)
        monkeypatch.setattr(EXEC, "_get_l2_ledger_writer", lambda: fake_writer)
        monkeypatch.setattr(EXEC, "load_ollama_screen_calibration", lambda **k: _enabled_calibration())
        store: list[dict[str, Any]] = []
        monkeypatch.setattr(EXEC.db_pool, "get_pg_conn", _conn_provider_factory(store))

        eng = _FakeEngine(cloud_text=json.dumps(_VALID_DIAGNOSE_OUTPUT))
        cap = _make_ml_cap(capability_id="ml_advisory.diagnose_leak")
        o = _orch_with_ml(cap, engine=eng)
        _run(o.dispatch_and_execute(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context=_diagnose_context(), coarse_subject="BTCUSDT", now=1000.0,
        ))
        # 至少解析過一次（dispatch + dispatch_and_execute 路徑）。
        assert seen_refs, "dispatch_and_execute 路徑必解析 contract version"
        none_resolutions = [s for s in seen_refs if s["contract_ref"] is None]
        assert none_resolutions == [], (
            "ml_advisory cap 的 contract-version 解析絕不可傳 contract_ref=None（branch-3 generic "
            f"fallback → D3 記錯 provenance）；buggy dispatch_and_execute 會出現 None 解析：{seen_refs}"
        )
        # 且每次解析都帶 cap 的真實 per-mode ref（diagnose 的 prompt_contract_ref）。
        assert all(s["contract_ref"] == "ml_advisory.diagnose_leak.v1" for s in seen_refs), seen_refs
        assert all(s["schema_ref"] == "ml_advisory.v1" for s in seen_refs), seen_refs

    def test_ledger_contract_ver_equals_cascade_threaded_value(self, monkeypatch):
        """端到端鏈閉合：orchestrator 解析的 contract_ver → thread 給 run_ml_advisory_cascade →
        executor _ledger → record_l2_call。三處同值（無中途被 None 覆蓋）。

        spy run_ml_advisory_cascade 抓 orchestrator thread 進 cascade 的 contract_ver，與最終
        D3-recorded 值比對相等（確認 thread 路徑無斷裂）。"""
        threaded: dict[str, Any] = {}
        real_cascade = EXEC.run_ml_advisory_cascade

        async def _spy_cascade(*, contract_ver, schema_ver, **kw):
            threaded["contract_ver"] = contract_ver
            threaded["schema_ver"] = schema_ver
            return await real_cascade(contract_ver=contract_ver, schema_ver=schema_ver, **kw)

        monkeypatch.setattr(EXEC, "run_ml_advisory_cascade", _spy_cascade)
        writer = _drive_dispatch_and_execute_real_registry(
            monkeypatch, capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak"
        )
        kwargs = _captured_ledger_kwargs(writer)
        assert threaded["contract_ver"] == "ml_advisory_diagnose.v1"
        assert kwargs["contract_ver"] == threaded["contract_ver"]  # thread 值 == D3 記錄值
        assert kwargs["schema_ver"] == threaded["schema_ver"]
