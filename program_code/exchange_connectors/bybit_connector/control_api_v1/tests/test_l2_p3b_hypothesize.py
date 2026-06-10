"""L2 Phase 3b — ml_advisory.hypothesize cascade（alpha-bearing）測試。驗「意圖」非僅行為。

覆蓋（對映 PA P3b §A/§E + QC B1 + MIT M3/M4）：
  - §G.2 cascade order：Ollama screen → Ollama generate（cheap）→ guard → novelty → math gate →
    cloud interpret survivors（cost only on survivors）。
  - math gate 是唯一 alpha validator（B1+DSR+PBO+leak+Q1）；LLM 永不驗 alpha。
  - promotion routing（§E.5）：pass → backlog sink；DEFER → backlog 標 non-promotable；
    fail → logged-and-dropped（不 sink）。
  - 0 新 live authority：sink 寫 genuinely-inert agent.lessons；0 order/lease/promote。
  - guard empty-mechanism clause（§E.4(b)）：空 mechanism → reject。
  - novelty dedupe（§E.4(c)）：dead_failure_mode 重複 → math gate DEFER（executor DB read）。
  - cloud interpret 只在 math gate pass（survivors only；DEFER/fail 不花 cloud）。

Mac-tested（mocked PG + fake engine；無真 DB/model）。Linux E4 + QC(B1) + MIT(M3/M4) owed。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# program_code.learning_engine 跨 package import（math gate stage 用；srv root = parents[5]）。
_SRV_ROOT = Path(__file__).resolve().parents[5]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))

from app import l2_ml_advisory_executor as EXEC


# ═══════════════════════════════════════════════════════════════════════════════
# fake engine：依 system_prompt 路由（hypothesize generate vs cloud interpret）
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
        self.recorded.append((in_tok, out_tok, model_tier))
        return 0.01


class _HypEngine:
    """fake engine：screen / generate / cloud-interpret 三類呼叫分別回可控回應（依 system_prompt）。

    screen_text：max_tokens<=screen 的呼叫（loose screen）。
    generate_text：system_prompt 是 hypothesize 模板的呼叫。
    interpret_text：system_prompt 是 interpret 模板的呼叫（survivor interpret）。
    """

    def __init__(self, *, screen_text="{\"verdict\":\"pass\"}", generate_text=None, interpret_text=None):
        self._cost_tracker = _FakeCostTracker()
        self._screen_text = screen_text
        self._generate_text = generate_text
        self._interpret_text = interpret_text
        self.calls: list[dict[str, Any]] = []

    def _resolve_effective_provider(self, *, base_provider, base_tier, role):
        return base_provider, base_tier

    async def _provider_complete(self, *, provider_name, tier, system_prompt, messages, tools, max_tokens, timeout):
        self.calls.append({"tier": tier, "max_tokens": max_tokens, "system_prompt": system_prompt})
        if max_tokens <= EXEC._SCREEN_MAX_TOKENS:
            text = self._screen_text
        elif "feature-hypothesis proposer" in system_prompt or "hypothesize" in system_prompt:
            text = self._generate_text
        else:
            text = self._interpret_text
        if text is None:
            return None
        return _FakeResponse(text)


class _CapturingConn:
    def __init__(self, store):
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


def _conn_provider_factory(store):
    def _provider():
        return _CapturingConn(store)
    return _provider


def _enabled_calibration():
    return EXEC.OllamaScreenCalibration(
        enabled=True, recall=0.92, threshold=0.85, benchmark_version="v1_test", reason="calibrated"
    )


def _valid_hypothesis_output():
    """合法 hypothesize 輸出（P4 v2 契約形：結構化 falsification 三欄 + primary_axis ∈
    signal_axes_used——guard clause F 強制；v1 自由字串形已被 F reject）。"""
    return {
        "mode": "hypothesize",
        "signal_axes_used": ["funding_rate", "adx_1h"],
        "feature_hypotheses": [
            {
                "hid": "h1",
                "statement": "funding skew predicts short-horizon mean reversion",
                "mechanism": "crowded longs pay funding; unwind reverts price",
                "falsification_test": {
                    "null_hypothesis": "funding skew has no predictive power for reversion",
                    "test_statistic": "deflated Sharpe of funding-sorted bucket spread",
                    "reject_condition": "DSR below threshold on pre-registered window",
                },
                "primary_axis": "funding_rate",
                "signal_axes_used": ["funding_rate"],
                "expected_direction": "short",
                "beta_neutralization_plan": "residualize candidate vs BTC + altcap basket",
            }
        ],
        "backlog_items": ["register funding-skew feature for B2 forward-OOS"],
    }


def _evidence_window():
    """P4：context 必帶 evidence 窗（pre-reg 釘窗 / debit_id / sealed 檢查），缺 = precheck 免費 DEFER。"""
    return {"window_start": "2025-01-01", "window_end": "2025-09-30"}


class _FakeAwc:
    """E1-A alpha_wealth_controller 的 import-點 fake（簽名 = PA §2.2 契約；本 branch A 檔
    未 merge，E4 全鏈於 merge 後驗真模組）。dsr_threshold_for 固定回 floor=0.95 保留
    legacy DSR 行為——threshold 真咬合在 test_l2_p4_online_fdr.py 另測。"""

    ALPHA_TARGET_DEFAULT = 0.05
    W0_GAMMA = 0.10
    PHI_REFUND = 1.0
    MIN_BATCH_SIZE_DEFAULT = 10
    SPEND_FRACTION_DEFAULT = 0.10

    @staticmethod
    def init_family_wealth(alpha_target: float = 0.05, gamma: float = 0.10) -> float:
        return gamma * alpha_target

    @staticmethod
    def assign_alpha_i(balance, *, alpha_target, min_batch_size, spend_fraction):
        cap = alpha_target / float(min_batch_size)
        alpha_i = min(spend_fraction * balance, cap)
        return None if alpha_i < 1e-6 else alpha_i

    @staticmethod
    def can_test(balance, alpha_i):
        return (balance - alpha_i) > 0.0

    @staticmethod
    def dsr_threshold_for(alpha_i, *, floor: float = 0.95) -> float:
        return floor


@pytest.fixture
def _fdr_machinery(monkeypatch):
    """P4 wealth/pre-reg/sealed 機構的注入（0 真連線 / 0 真 learning_engine import）。

    回 dict 捕捉 debits / preregs；dead-mode 鑄造走真 _mint_dead_mode_lesson（由
    sink_conn_provider 捕捉，不在此 mock）。
    """
    import app.l2_alpha_wealth_store as STORE

    captured: dict[str, Any] = {"debits": [], "preregs": []}
    monkeypatch.setattr(EXEC, "_resolve_wealth_controller", lambda: _FakeAwc)
    monkeypatch.setattr(
        EXEC, "_check_sealed_boundary",
        lambda strategy, symbol, we, conn: (False, ["no_sealed_split_for_cell"]),
    )

    def _fake_prereg(**kw):
        captured["preregs"].append(kw)
        return STORE.PreRegistrationOutcome(ok=True, pre_reg_id=11, spec_sha256="ab" * 32)

    def _fake_debit(**kw):
        captured["debits"].append(kw)
        return STORE.DebitOutcome(ok=True, debit_id=kw["debit_id"])

    monkeypatch.setattr(STORE, "register_pre_registration", _fake_prereg)
    monkeypatch.setattr(STORE, "ensure_family_initialized", lambda *a, **kw: None)
    monkeypatch.setattr(STORE, "get_family_balance", lambda *a, **kw: 0.005)
    monkeypatch.setattr(STORE, "record_debit", _fake_debit)
    return captured


def _available_axes():
    return ["funding_rate", "adx_1h", "bb_width_pct", "atr_pct"]


def _math_gate_inputs_pass():
    """math gate inputs 使全 stage pass（clean neutral candidate + 足樣本 + genuine CPCV + leak-free）。

    ★ PBO 需 genuine CPCV peers（≥2 candidate，total≥320，PBO<0.5）才可 pass；無 peer → honest-DEFER
    （承 2026-06-08 Gap-A：捏造 peer 是 theater）。此 fixture 提供「真實」CPCV returns 讓全閘可 pass。
    """
    import random
    import numpy as np
    random.seed(7)
    N = 250
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    cand = {i: 0.0003 + random.gauss(0, 0.003) for i in range(N)}
    mask = {i: (btc[i] < -0.01) for i in range(N)}
    # genuine CPCV peers：候選 0 真有 edge（consistent），其餘 noise → PBO<0.5。
    np.random.seed(1)
    cpcv = [
        np.random.normal(0.5, 1.0, 200),  # genuine best
        np.random.normal(0.0, 1.0, 200),
        np.random.normal(0.0, 1.0, 200),
    ]
    return cand, {
        "btc_returns": btc, "altcap_returns": alt, "down_market_mask": mask,
        "n_trades_oos": 200, "observed_sharpe": 3.0, "n_trials": 5,
        "cpcv_oos_returns_per_split": cpcv,
        "shift1_compliance_leak_free": True, "bar": "daily",
    }


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def _mock_ledger(monkeypatch):
    writer = MagicMock()
    monkeypatch.setattr(EXEC, "_get_l2_ledger_writer", lambda: writer)
    return writer


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """防 prod 污染鐵閘（P0，2026-06-10）：本檔 sink 測試曾只 mock ledger、漏 mock lessons
    的 DB 連線——Mac 無 PG 時 fail-soft 吞錯假綠，但在連得上真 PG 的環境（Linux E4 parity /
    deploy re-test）每輪把 3 條 fixture 假資料寫進 prod agent.lessons（7 輪共 21 rows，污染
    M4 novelty/dead-modes 語料，已清）。教訓：「mock 不掩蓋邏輯」的對偶是「連線層必隔離」。

    此 autouse 把 executor 模組引用的 db_pool.get_pg_conn 換成 MagicMock：content 構造 /
    redact / INSERT 參數綁定全真實走（邏輯不被掩蓋），只攔真連線。需要斷言 INSERT 參數的
    測試請顯式注入 conn_provider（write_ml_advisory_advisory_sink 參數，優先於本 fixture）。
    """
    fake_conn_cm = MagicMock()  # MagicMock 自帶 __enter__/__exit__，with provider() as conn 可用
    monkeypatch.setattr(EXEC.db_pool, "get_pg_conn", lambda: fake_conn_cm)
    return fake_conn_cm


# ═══════════════════════════════════════════════════════════════════════════════
# §G.2 cascade order + math gate 整合
# ═══════════════════════════════════════════════════════════════════════════════


def test_hypothesize_pass_routes_to_backlog_sink(_mock_ledger, _fdr_machinery):
    """math gate pass → backlog sink（agent.lessons）+ cloud interpret survivor（cost on survivor）。
    P4：pass = conducted → 恰一筆 debit（MIT #3）。"""
    cand, gate_inputs = _math_gate_inputs_pass()
    eng = _HypEngine(
        generate_text=json.dumps(_valid_hypothesis_output()),
        interpret_text=json.dumps({"mode": "interpret_result",
                                   "result_interpretation": {"reading": "ok", "confidence": "low"}}),
    )
    store: list[dict[str, Any]] = []
    res = _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={"candidate_returns": cand, "math_gate_inputs": gate_inputs,
                 "evidence_window": _evidence_window()}, engine=eng,
        contract_ver="ml_advisory_hypothesize.v2", schema_ver="ml_advisory_schema.v1",
        available_signal_axes=_available_axes(), calibration=_enabled_calibration(),
        sink_conn_provider=_conn_provider_factory(store),
    ))
    assert res.math_gate_verdict == "pass", f"reasons={res.math_gate_reasons}"
    assert res.stage == "backlog_written"
    assert res.ok is True
    # sink INSERT 到 agent.lessons（genuinely inert）。
    assert any("INSERT INTO agent.lessons" in s["sql"] for s in store)
    # cloud interpret 跑了（survivor；math gate pass 後）。
    assert res.cloud_called is True
    # P4：conducted（pass）→ 恰一筆 debit（k_for_dsr=n_eff 同源由 store 層測試鎖）。
    assert len(_fdr_machinery["debits"]) == 1


def test_hypothesize_b1_fail_logged_and_dropped_no_sink(_mock_ledger, _fdr_machinery):
    """math gate fail（B1 down-beta）→ logged-and-dropped（D3 記，不 sink）。"""
    import random
    random.seed(2)
    N = 200
    btc = {i: random.gauss(-0.001, 0.025) for i in range(N)}
    alt = {i: btc[i] * 0.6 + random.gauss(0, 0.02) for i in range(N)}
    down_idx = set(i for i in range(N) if btc[i] < -0.01)
    cand = {i: (0.8 * btc[i] if i in down_idx else 0.0005) for i in range(N)}
    mask = {i: (i in down_idx) for i in range(N)}
    gate_inputs = {
        "btc_returns": btc, "altcap_returns": alt, "down_market_mask": mask,
        "n_trades_oos": 200, "observed_sharpe": 3.0, "n_trials": 5,
        "shift1_compliance_leak_free": True, "bar": "daily",
    }
    eng = _HypEngine(generate_text=json.dumps(_valid_hypothesis_output()))
    store: list[dict[str, Any]] = []
    res = _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={"candidate_returns": cand, "math_gate_inputs": gate_inputs,
                 "evidence_window": _evidence_window()}, engine=eng,
        contract_ver="x", schema_ver="y", available_signal_axes=_available_axes(),
        calibration=_enabled_calibration(), sink_conn_provider=_conn_provider_factory(store),
    ))
    assert res.math_gate_verdict == "fail"
    assert res.stage == "math_gate_failed"
    assert res.ok is False
    # fail → 不寫 advisory sink（logged-and-dropped）；但 P4 FIX-1.3 鑄 dead-mode lesson
    # （source='dead_mode_seed'，dict 參數形）——兩者都進 agent.lessons，按 source 區分。
    sink_inserts = [
        s for s in store
        if "INSERT INTO agent.lessons" in s["sql"] and isinstance(s["params"], tuple)
    ]
    assert not sink_inserts  # advisory sink（位置參數形 + source='ml_advisory'）未寫
    dead_mode_inserts = [
        s for s in store
        if isinstance(s["params"], dict) and s["params"].get("source") == "dead_mode_seed"
    ]
    assert len(dead_mode_inserts) == 1  # FIX-1.3：被證偽假說鑄 dead-mode（novelty 閉環）
    assert "null_hypothesis=" in dead_mode_inserts[0]["params"]["content"]
    # cloud interpret 沒跑（cost only on survivors；fail 不花 cloud）。
    assert res.cloud_called is False
    # P4：fail = conducted → 必有 debit（MIT #3）。
    assert len(_fdr_machinery["debits"]) == 1


def test_hypothesize_defer_writes_backlog_non_promotable(_mock_ledger):
    """leak producers 皆缺 → P4 precheck 免費 DEFER（FIX-3.1：注定 DEFER 的 run 不渲染
    DSR、不入帳、不觸 wealth store）→ backlog 標 gate_verdict=DEFER（non-promotable）。

    本測試刻意「不」掛 _fdr_machinery：precheck 在 pre-reg/wealth 之前短路，真 store
    模組不被觸碰（store 函數若被呼會因 fake conn 缺 fetchone 而炸——綠 = 結構性未觸）。
    """
    cand, gate_inputs = _math_gate_inputs_pass()
    gate_inputs.pop("shift1_compliance_leak_free")  # 兩 leak producer 皆缺 → precheck doom
    eng = _HypEngine(generate_text=json.dumps(_valid_hypothesis_output()))
    store: list[dict[str, Any]] = []
    res = _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={"candidate_returns": cand, "math_gate_inputs": gate_inputs,
                 "evidence_window": _evidence_window()}, engine=eng,
        contract_ver="x", schema_ver="y", available_signal_axes=_available_axes(),
        calibration=_enabled_calibration(), sink_conn_provider=_conn_provider_factory(store),
    ))
    assert res.math_gate_verdict == "DEFER"
    assert "precheck_input_unavailable" in res.math_gate_reasons
    assert res.stage == "backlog_written"  # DEFER 仍 sink（標 non-promotable）
    # sink payload 帶 gate_verdict DEFER。
    insert = [s for s in store if "INSERT INTO agent.lessons" in s["sql"]]
    assert insert
    # cloud interpret 沒跑（DEFER 非 survivor）。
    assert res.cloud_called is False


def test_hypothesize_cost_only_on_survivors_cloud_not_called_on_defer(_mock_ledger):
    """cost only on survivors：math gate DEFER → cloud interpret 不跑（只 screen+generate）。"""
    cand, gate_inputs = _math_gate_inputs_pass()
    gate_inputs.pop("shift1_compliance_leak_free")  # → DEFER
    eng = _HypEngine(generate_text=json.dumps(_valid_hypothesis_output()),
                     interpret_text=json.dumps({"mode": "interpret_result", "result_interpretation": {}}))
    _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={"candidate_returns": cand, "math_gate_inputs": gate_inputs}, engine=eng,
        contract_ver="x", schema_ver="y", available_signal_axes=_available_axes(),
        calibration=_enabled_calibration(),
    ))
    # 只 screen + generate（2 calls）；無 cloud interpret（第 3 call）。
    interpret_calls = [c for c in eng.calls if c["max_tokens"] > EXEC._SCREEN_MAX_TOKENS
                       and "feature-hypothesis proposer" not in c["system_prompt"]]
    assert interpret_calls == []


# ═══════════════════════════════════════════════════════════════════════════════
# guard empty-mechanism + novelty
# ═══════════════════════════════════════════════════════════════════════════════


def test_hypothesize_empty_mechanism_guard_rejects(_mock_ledger):
    """空 mechanism → guard reject（curve-fit）→ 不 sink、math gate 不跑。"""
    bad = _valid_hypothesis_output()
    bad["feature_hypotheses"][0]["mechanism"] = ""  # 空機制
    eng = _HypEngine(generate_text=json.dumps(bad))
    store: list[dict[str, Any]] = []
    res = _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={}, engine=eng, contract_ver="x", schema_ver="y",
        available_signal_axes=_available_axes(), calibration=_enabled_calibration(),
        sink_conn_provider=_conn_provider_factory(store),
    ))
    assert res.guard_verdict == "reject"
    assert res.stage == "guard_rejected"
    assert not any("INSERT INTO agent.lessons" in s["sql"] for s in store)


def test_hypothesize_novelty_duplicate_defers(monkeypatch, _mock_ledger, _fdr_machinery):
    """novelty: dead_failure_mode 重複 → math gate DEFER（executor DB read，§E.4(c)）。"""
    cand, gate_inputs = _math_gate_inputs_pass()
    eng = _HypEngine(generate_text=json.dumps(_valid_hypothesis_output()))

    # mock retrieve_lessons 回一個 dead_mode（模擬 near-duplicate）。
    async def _fake_retrieve(symbol, hint, lesson_type=None):
        assert lesson_type == "dead_mode"
        return [{"id": 1, "content": "funding skew is alpha (was beta)"}]
    import app.layer2_critic as _critic
    monkeypatch.setattr(_critic, "retrieve_lessons", _fake_retrieve)

    res = _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={"candidate_returns": cand, "math_gate_inputs": gate_inputs,
                 "evidence_window": _evidence_window()}, engine=eng,
        contract_ver="x", schema_ver="y", available_signal_axes=_available_axes(),
        calibration=_enabled_calibration(),
    ))
    assert res.novelty == "duplicate"
    assert res.math_gate_verdict == "DEFER"
    assert "duplicate_of_dead_failure_mode" in res.math_gate_reasons


def test_hypothesize_generate_unavailable_fail_soft(_mock_ledger):
    """Ollama generate 不可用（回 None）→ fail-soft（D3 記 error，不 sink）。"""
    eng = _HypEngine(generate_text=None)  # generate 回 None
    store: list[dict[str, Any]] = []
    res = _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={}, engine=eng, contract_ver="x", schema_ver="y",
        available_signal_axes=_available_axes(), calibration=_enabled_calibration(),
        sink_conn_provider=_conn_provider_factory(store),
    ))
    assert res.ok is False
    assert res.stage == "generate_unavailable_or_unparsable"
    assert not any("INSERT INTO agent.lessons" in s["sql"] for s in store)


def test_hypothesize_screen_reject_short_circuits(_mock_ledger):
    """Ollama screen reject → 零 generate/cloud call（cost only on survivors）。"""
    eng = _HypEngine(screen_text='{"verdict":"skip","reason":"empty run"}',
                     generate_text=json.dumps(_valid_hypothesis_output()))
    res = _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={}, engine=eng, contract_ver="x", schema_ver="y",
        available_signal_axes=_available_axes(), calibration=_enabled_calibration(),
    ))
    assert res.stage == "screen_rejected"
    # 只 screen call（1 call）；無 generate。
    assert len(eng.calls) == 1


def test_hypothesize_pbo_single_config_honest_defers(_mock_ledger, _fdr_machinery):
    """PBO single-config（無 genuine CPCV peers）→ honest-DEFER（不捏造 peer；承 Gap-A ruling）。

    為什麼這條重要：B1/DSR 即使 pass，single-config 候選的 PBO 必 honest-DEFER（genuine peer
    owed to A-full Rust replay, P4+），故 P3b 單配置候選 overall 至多 DEFER（誠實，非吐 alpha）。
    """
    cand, gate_inputs = _math_gate_inputs_pass()
    gate_inputs.pop("cpcv_oos_returns_per_split")  # 無 genuine CPCV peers → PBO honest-DEFER
    eng = _HypEngine(generate_text=json.dumps(_valid_hypothesis_output()))
    res = _run(EXEC.run_ml_advisory_cascade(
        capability_id="ml_advisory.hypothesize", mode="hypothesize",
        context={"candidate_returns": cand, "math_gate_inputs": gate_inputs,
                 "evidence_window": _evidence_window()}, engine=eng,
        contract_ver="x", schema_ver="y", available_signal_axes=_available_axes(),
        calibration=_enabled_calibration(),
    ))
    assert res.math_gate_verdict == "DEFER"
    assert "pbo_single_config_honest_defer" in res.math_gate_reasons
    # P4 MIT #3 golden：dsr=pass ∧ overall=DEFER（single-config PBO honest-DEFER）⇒ 必有 debit
    # （α-bearing 統計量已與 threshold 比較 = conducted；免費 re-look 通道封死）。
    assert len(_fdr_machinery["debits"]) == 1


def test_hypothesize_executor_zero_order_lease_promote():
    """鐵律 grep：P3b 加 hypothesize 後 executor 真碼仍 0 order/lease/promote/live-config 引用。

    為什麼重新驗：P3b 大幅擴 executor（math gate / generate / novelty / hypothesize cascade）；
    確認 0 新 live authority 在 raw token 層仍成立（不靠註解約束）。
    """
    import ast
    src = (PROJECT_ROOT / "app" / "l2_ml_advisory_executor.py").read_text(encoding="utf-8")
    # 剝註解 + 字串，只留真碼 token。
    import io
    import tokenize
    toks = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        toks.append(tok.string)
    code = " ".join(toks)
    for forbidden in ("IntentProcessor", "submit_intent", "place_order", "acquire_lease",
                      "promote_tier", "live_execution_allowed", "OPENCLAW_ALLOW_MAINNET",
                      "execution_authority", "system_mode", "can_modify_live_config"):
        assert forbidden not in code, f"P3b executor 不該含 {forbidden}（0 新 live authority）"
