"""
L2 Advisory Mesh — Phase 2（Orchestrator + registry + contracts + guard + admission +
adjudication + LANE_DIRECTION）測試。驗「意圖」非僅行為（CLAUDE Operating Style 9）。

覆蓋（對映 PA P2 設計 §M acceptance + execution-plan §2 CC stress-tests）：
  - LANE_DIRECTION / effective_autonomy（CC 5/10 linchpin）：無 "live" key；STEP-1 expand→MANUAL
    在函數頂、非-overridable；tier/posture 永不解鎖 expand。mutation 驗：改 STEP-1 → 測試紅。
  - registry loader（CC 16）：unknown field reject；enabled 預設 false；reject 宣告 autonomy_level；
    reject can_auto_deploy_to_paper-as-posture；reject lane:"live"；reject min_tier 非法。
  - C1：orchestrator + advisory-loop 模塊 grep 0 promote_tier / autonomy-raiser。
  - C2：orchestrator/applier grep 0 `if can_auto_deploy_to_paper` posture 分支。
  - F.2（CC 6）：adjudicator 內 0 model 呼叫；gate reject 永勝 L2 recommend；contract > expand。
  - guard（§E）：reject → 不 route；deterministic（無 model）；clamp 夾值；負成本 reject。
  - admission（§F.1）：storm 不破 DOC-08 $2/day（debounce off 亦然）；dedup/debounce；
    per-cap 日上限 NO_ADVICE；suppressed 記 trigger_decision。
  - fail-safe（§H）：HEALTHY→...→GLOBAL_CONSERVATIVE；每態減 L2 能力；0 live-enabling write。
  - 接線 reachability：layer2_engine wiring delta 解析 contract registry（manual 零回歸）。

Mac-tested（mocked PG via conn_provider 注入；無真 DB）。Linux E4 regression + E3 對抗驗 owed。
"""

import inspect
import io
import sys
import tokenize
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import l2_advisory_orchestrator as ORCH
from app import l2_capability_registry as REG
from app import l2_conflict_adjudicator as ADJ
from app import l2_out_of_bound_guard as GUARD
from app import l2_prompt_contract_registry as CONTRACTS
from app import l2_call_ledger_writer as LEDGER
from app.learning_tier_gate import LearningTier


def _code_only(path: Path) -> str:
    """剝除註解 + docstring，只留「真碼」token 文本。

    為什麼：C1/C2/F.2 的不變式是「無 code 引用/呼叫禁字」，**非**「註解不得提及」。
    MODULE_NOTE / docstring 合法地解釋「為何禁某字」（如 'orchestrator 不呼 promote_tier'）；
    那些 prose 不是 code reference。CC 概念上 grep 的是真 `if`/呼叫，不是散文。用 tokenize
    抽出 NAME/OP/NUMBER（丟 COMMENT/STRING）後拼回，得到僅含真碼 identifier 的文本。
    """
    src = path.read_text(encoding="utf-8")
    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            if tok.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                out.append("\n")
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return src  # 退化（理論不會發生，全檔已 py_compile 過）
    return " ".join(out)


# C1/C2/F.2 grep：用「真碼 only」文本（剝註解/docstring）驗無禁字 code 引用。
_APP_DIR = PROJECT_ROOT / "app"
_ORCH_CODE = _code_only(_APP_DIR / "l2_advisory_orchestrator.py")
_REG_CODE = _code_only(_APP_DIR / "l2_capability_registry.py")
_ADJ_CODE = _code_only(_APP_DIR / "l2_conflict_adjudicator.py")
_GUARD_CODE = _code_only(_APP_DIR / "l2_out_of_bound_guard.py")


def _make_cap(**overrides) -> REG.L2Capability:
    """建一個合法 capability（測試輔助；enabled 預設 True 以便測 admission 後段）。"""
    base = dict(
        capability_id="test_cap",
        enabled=True,
        min_tier="L1",
        model_tier="local_sentinel",
        lane="research",
    )
    base.update(overrides)
    return REG.L2Capability(**base)


# ═══════════════════════════════════════════════════════════════════════════════
# LANE_DIRECTION + effective_autonomy — CC stress-test 5/10 linchpin
# ═══════════════════════════════════════════════════════════════════════════════


class TestLaneDirectionLinchpin:
    def test_no_live_key_in_lane_direction(self):
        """LANE_DIRECTION 無 'live' key（live 不可從任何 auto 路徑到達）。"""
        assert "live" not in REG.LANE_DIRECTION
        # 也沒有任何 value 是 "live"
        assert "live" not in set(REG.LANE_DIRECTION.values())

    def test_step1_expand_returns_manual_first_and_non_overridable(self):
        """STEP-1 expand→MANUAL 在函數頂；即便 tier 充足 + Standard posture 也 MANUAL。"""
        cap = _make_cap(lane="demo_stage1")  # demo_stage1 = expand
        # 即便最高 tier + Standard posture（最寬鬆），expand 仍 MANUAL（STEP-1 攔截）。
        out = REG.effective_autonomy(
            cap, current_tier=LearningTier.L5, posture="Standard", tier_flag_value=True
        )
        assert out == "MANUAL"

    def test_step1_source_is_first_if_in_function(self):
        """grep-style：effective_autonomy 第一個 if（剝 docstring 後）就是 expand→MANUAL。

        剝 docstring：docstring 本身會提及 current_tier/posture（解釋語義），故取「真碼 only」
        驗 STEP-1 的 expand-check 在任何 current_tier/posture 比較「之前」出現於 code。
        """
        src = inspect.getsource(REG.effective_autonomy)
        # 剝掉首個 docstring（"""..."""）只留 code body。
        code = src
        if '"""' in code:
            first = code.index('"""')
            second = code.index('"""', first + 3)
            code = code[:first] + code[second + 3:]
        idx_step1 = code.find('LANE_DIRECTION[cap.lane] == "expand"')
        idx_tier = code.find("current_tier <")
        idx_posture = code.find('posture ==')
        assert idx_step1 != -1, "STEP-1 LANE_DIRECTION==expand 必存在於 code"
        assert idx_step1 < idx_tier, "STEP-1 必在 tier 比較之前（code 順序）"
        assert idx_step1 < idx_posture, "STEP-1 必在 posture 比較之前（code 順序）"

    def test_contract_lane_not_forced_manual(self):
        """contract lane（risk_tighten）非 promotion-class → 不被 STEP-1 強制 MANUAL。"""
        cap = _make_cap(lane="risk_tighten")
        out = REG.effective_autonomy(
            cap, current_tier=LearningTier.L1, posture="Conservative"
        )
        assert out == "AUTO_VIA_GATE"  # 收緊 auto（被 deterministic governor 夾）

    def test_neutral_lane_auto_via_gate(self):
        cap = _make_cap(lane="research")
        out = REG.effective_autonomy(cap, current_tier=LearningTier.L1, posture="Standard")
        assert out == "AUTO_VIA_GATE"

    def test_tier_locked_when_tier_insufficient(self):
        """min_tier 高於 current_tier → TIER_LOCKED（refuse，不降級）。"""
        cap = _make_cap(lane="research", min_tier="L4")
        out = REG.effective_autonomy(cap, current_tier=LearningTier.L1, posture="Standard")
        assert out == "TIER_LOCKED"

    def test_conservative_posture_promotion_class_forced_manual(self):
        """Conservative + promotion-class（demo_stage1）→ MANUAL（即便 expand 已先攔，雙保險語義）。"""
        cap = _make_cap(lane="demo_stage1")
        out = REG.effective_autonomy(
            cap, current_tier=LearningTier.L5, posture="Conservative", tier_flag_value=True
        )
        assert out == "MANUAL"

    def test_mutation_bite_step1_removed_would_break(self):
        """mutation 驗：若 STEP-1 不存在，demo_stage1+L5+Standard 會錯誤回 AUTO_VIA_GATE。

        此測試斷言「有 STEP-1」必得 MANUAL；移除 STEP-1（mutation）→ 走 STEP-3，但 STEP-3
        只在 Conservative 觸發，Standard 下會漏 → 證明 STEP-1 是 Standard 下唯一防線。
        """
        cap = _make_cap(lane="demo_stage1")
        # Standard posture 下 STEP-3 不觸發；唯 STEP-1 攔得住。
        out = REG.effective_autonomy(
            cap, current_tier=LearningTier.L5, posture="Standard", tier_flag_value=True
        )
        assert out == "MANUAL", "STEP-1 是 Standard posture 下 expand→MANUAL 的唯一防線"


# ═══════════════════════════════════════════════════════════════════════════════
# Registry loader — CC stress-test 16 + loader-reject
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegistryLoader:
    def test_enabled_defaults_false(self):
        """省略 enabled → false（fail-closed 預設）。"""
        cap = REG.L2Capability(capability_id="x", lane="research")
        assert cap.enabled is False

    def test_unknown_field_rejected(self):
        """unknown field → reject（extra='forbid'）。"""
        with pytest.raises(Exception):
            REG.L2Capability(capability_id="x", lane="research", bogus_field=1)

    def test_lane_live_rejected(self):
        """lane='live' → reject（無 live lane；live 不可達）。"""
        with pytest.raises(Exception):
            REG.L2Capability(capability_id="x", lane="live")

    def test_lane_unknown_rejected(self):
        """lane 不在 LANE_DIRECTION → reject（每 lane 必 resolve direction）。"""
        with pytest.raises(Exception):
            REG.L2Capability(capability_id="x", lane="risk_loosen")

    def test_min_tier_invalid_rejected(self):
        with pytest.raises(Exception):
            REG.L2Capability(capability_id="x", lane="research", min_tier="L9")

    def test_loader_rejects_declared_autonomy_level(self, tmp_path):
        """loader 拒宣告 autonomy_level 的 config（autonomy 是 DERIVED）。"""
        toml = tmp_path / "reg.toml"
        toml.write_text(
            '[[capability]]\n'
            'capability_id = "x"\n'
            'enabled = false\n'
            'lane = "research"\n'
            'autonomy_level = "AUTO"\n',
            encoding="utf-8",
        )
        with pytest.raises(REG.L2RegistryLoadError) as ei:
            REG.load_capability_registry(toml)
        assert "autonomy_level" in str(ei.value)

    def test_loader_rejects_can_auto_deploy_as_posture_gate(self, tmp_path):
        """loader 拒把 can_auto_deploy_to_paper 當 posture gate 的 config（C2）。"""
        toml = tmp_path / "reg.toml"
        toml.write_text(
            '[[capability]]\n'
            'capability_id = "x"\n'
            'enabled = false\n'
            'lane = "research"\n'
            'tier_capability_flag = "can_auto_deploy_to_paper"\n',
            encoding="utf-8",
        )
        with pytest.raises(REG.L2RegistryLoadError) as ei:
            REG.load_capability_registry(toml)
        assert "can_auto_deploy_to_paper" in str(ei.value)

    def test_loader_rejects_lane_live_in_toml(self, tmp_path):
        toml = tmp_path / "reg.toml"
        toml.write_text(
            '[[capability]]\ncapability_id = "x"\nlane = "live"\n', encoding="utf-8"
        )
        with pytest.raises(REG.L2RegistryLoadError):
            REG.load_capability_registry(toml)

    def test_loader_rejects_unknown_top_level_key(self, tmp_path):
        toml = tmp_path / "reg.toml"
        toml.write_text('[bogus]\nx = 1\n', encoding="utf-8")
        with pytest.raises(REG.L2RegistryLoadError):
            REG.load_capability_registry(toml)

    def test_default_checked_in_toml_loads_empty_skeleton(self):
        """checked-in 預設 TOML 載入成功且 capabilities 空（P2 skeleton）。"""
        reg = REG.load_capability_registry()
        assert reg.capabilities == {}
        assert reg.enabled_capabilities() == []

    def test_missing_toml_returns_empty_failclosed(self, tmp_path):
        """TOML 不存在 → 回空 registry（fail-closed，不崩潰）。"""
        reg = REG.load_capability_registry(tmp_path / "does_not_exist.toml")
        assert reg.capabilities == {}

    def test_valid_capability_loads(self, tmp_path):
        """合法 stanza 完整載入（含 trigger/budget）。"""
        toml = tmp_path / "reg.toml"
        toml.write_text(
            '[[capability]]\n'
            'capability_id = "ml_advisory"\n'
            'enabled = true\n'
            'min_tier = "L1"\n'
            'model_tier = "cloud_l2"\n'
            'lane = "research"\n'
            '[capability.trigger]\n'
            'kind = "event"\n'
            'spec = "ml:training_complete"\n'
            'debounce_secs = 900\n'
            '[capability.budget]\n'
            'per_call_usd_cap = 0.5\n'
            'daily_usd_cap = 1.0\n',
            encoding="utf-8",
        )
        reg = REG.load_capability_registry(toml)
        cap = reg.get("ml_advisory")
        assert cap is not None
        assert cap.enabled is True
        assert cap.trigger.debounce_secs == 900
        assert cap.budget.daily_usd_cap == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# C1 / C2 — grep 原始碼（驗 0 promote_tier / 0 posture-branch on can_auto_deploy）
# ═══════════════════════════════════════════════════════════════════════════════


class TestCarbonLayerGrep:
    def test_c1_orchestrator_zero_promote_tier(self):
        """C1：orchestrator 真碼 0 個 promote_tier / autonomy-raiser refs（剝註解後）。"""
        assert "promote_tier" not in _ORCH_CODE
        assert "set_autonomy_level" not in _ORCH_CODE

    def test_c1_no_order_or_lease_authority(self):
        """orchestrator 真碼無 order / trading-lease authority（root principle 1/3）。"""
        for forbidden in ("IntentProcessor", "submit_intent", "place_order"):
            assert forbidden not in _ORCH_CODE, f"orchestrator 真碼不應 import/呼 {forbidden}"
        # acquire_lease（trading scope）真碼不得出現。
        assert "acquire_lease" not in _ORCH_CODE

    def test_c1_no_live_config_write(self):
        """orchestrator 真碼不碰 live-config 硬邊界（剝註解後）。"""
        for forbidden in (
            "live_execution_allowed",
            "OPENCLAW_ALLOW_MAINNET",
            "execution_authority",
            "system_mode",
        ):
            assert forbidden not in _ORCH_CODE, f"orchestrator 真碼不應觸 {forbidden}"

    def test_c2_no_posture_branch_on_can_auto_deploy(self):
        """C2：orchestrator + registry 真碼 0 個 can_auto_deploy_to_paper 引用（剝註解後）。

        註解合法地解釋「為何不用它」；真碼（剝註解/docstring）完全不該出現此 identifier
        ——更嚴於「無 if 分支」，直接確認 code 零引用。
        """
        for code in (_ORCH_CODE, _REG_CODE):
            assert "can_auto_deploy_to_paper" not in code, \
                "真碼不得引用 can_auto_deploy_to_paper（C2；註解解釋除外）"

    def test_f2_adjudicator_zero_model_call(self):
        """F.2：adjudicator 真碼內 0 model 呼叫（run_session / LLM client；剝註解後）。"""
        low = _ADJ_CODE.lower()
        for forbidden in ("run_session", "LocalLLMClient", "provider_complete", "ollama", "anthropic"):
            assert forbidden.lower() not in low, \
                f"adjudicator 真碼不應含 model 呼叫 {forbidden}"

    def test_guard_zero_model_call(self):
        """guard 確定性：真碼內無 model 呼叫（剝註解後）。"""
        for forbidden in ("run_session", "LocalLLMClient", "provider_complete"):
            assert forbidden not in _GUARD_CODE


# ═══════════════════════════════════════════════════════════════════════════════
# Conflict adjudication — CC stress-test 6（fixed precedence，no model）
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdjudication:
    def test_gate_reject_always_beats_l2_recommend(self):
        """gate reject 永勝 L2 recommend（model 不 override 失敗 gate）。"""
        out = ADJ.adjudicate_vs_gate(gate_verdict="reject", l2_recommendation="recommend")
        assert out == "a_wins"  # gate 勝

    def test_gate_pass_lets_l2_proceed(self):
        out = ADJ.adjudicate_vs_gate(gate_verdict="pass", l2_recommendation="recommend")
        assert out == "b_wins"  # gate 未否決，L2 續走自身 gate

    def test_contract_beats_expand_same_target(self):
        """contract（收緊）勝 expand（晉升）同 target。"""
        a = ADJ.Proposal(capability_id="risk", lane="risk_tighten", target="BTCUSDT")
        b = ADJ.Proposal(capability_id="ml", lane="demo_stage1", target="BTCUSDT")
        out, reason = ADJ.adjudicate_cross_capability(a, b)
        assert out == "a_wins"  # contract a 勝
        assert "direction_precedence" in reason

    def test_orthogonal_targets_both_proceed(self):
        a = ADJ.Proposal(capability_id="x", lane="research", target="BTCUSDT")
        b = ADJ.Proposal(capability_id="y", lane="research", target="ETHUSDT")
        out, _ = ADJ.adjudicate_cross_capability(a, b)
        assert out == "both_proceed"

    def test_same_direction_stricter_magnitude_wins(self):
        a = ADJ.Proposal(capability_id="x", lane="risk_tighten", target="BTC", magnitude=0.5)
        b = ADJ.Proposal(capability_id="y", lane="risk_tighten", target="BTC", magnitude=0.2)
        out, reason = ADJ.adjudicate_cross_capability(a, b)
        assert out == "a_wins"
        assert reason == "stricter_magnitude"

    def test_unresolvable_escalates_no_auto_apply(self):
        """無法解（同 rank 同 magnitude）→ escalate（fail-closed，NO auto-apply）。"""
        a = ADJ.Proposal(capability_id="x", lane="risk_tighten", target="BTC", magnitude=0.5)
        b = ADJ.Proposal(capability_id="y", lane="risk_tighten", target="BTC", magnitude=0.5)
        out, reason = ADJ.adjudicate_cross_capability(a, b)
        assert out == "escalate"

    def test_precedence_is_literal_dict(self):
        """PRECEDENCE 是 literal dict（非 model 判斷）；contract>neutral>expand。"""
        assert ADJ.PRECEDENCE["contract"] > ADJ.PRECEDENCE["expand"]
        assert ADJ.PRECEDENCE["contract"] > ADJ.PRECEDENCE["neutral"]


# ═══════════════════════════════════════════════════════════════════════════════
# Out-of-bound guard — §E（deterministic，pre-proposal）
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuard:
    def test_pass_clean_output(self):
        r = GUARD.guard_output({"action": "hold", "leverage": 2.0, "size": 0.05})
        assert r.verdict == "pass"

    def test_none_output_rejected(self):
        r = GUARD.guard_output(None)
        assert r.verdict == "reject"
        assert "schema_nonconformant" in r.kinds_hit

    def test_negative_cost_rejected(self):
        """負成本 → reject（成本不可為負，幻覺向量）。"""
        r = GUARD.guard_output({"action": "buy", "total_cost_bps": -5})
        assert r.verdict == "reject"
        assert "negative_cost" in r.kinds_hit

    def test_leverage_clamped(self):
        """leverage 50x → clamp 到 bound；clamped_output 是夾值。"""
        r = GUARD.guard_output({"action": "buy", "leverage": 50.0})
        assert r.verdict == "clamp"
        assert r.clamped_output["leverage"] == 10.0
        assert "leverage_clamped" in r.kinds_hit

    def test_size_fraction_clamped(self):
        r = GUARD.guard_output({"action": "buy", "size_fraction": 0.80})
        assert r.verdict == "clamp"
        assert r.clamped_output["size_fraction"] == 0.10

    def test_invented_data_axis_rejected(self):
        """引用 available_signal_axes 之外的軸 → reject（no inventing data）。"""
        r = GUARD.guard_output(
            {"action": "buy", "referenced_signal_axes": ["funding", "ufo_signal"]},
            context={"available_signal_axes": ["funding", "oi"]},
        )
        assert r.verdict == "reject"
        assert any("invented_data_axis" in k for k in r.kinds_hit)

    def test_nan_leverage_rejected(self):
        r = GUARD.guard_output({"action": "buy", "leverage": float("nan")})
        assert r.verdict == "reject"


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrator admission — §F.1 storm control + DOC-08 $2/day
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeTracker:
    """注入用：可控的 check_daily_budget（測 storm-control / budget gate）。"""

    def __init__(self, allowed: bool = True, remaining: float = 2.0):
        self._allowed = allowed
        self._remaining = remaining
        self.calls = 0

    def check_daily_budget(self):
        self.calls += 1
        return self._allowed, self._remaining


def _orch_with(cap: REG.L2Capability, *, tracker=None, posture="Standard", tier=LearningTier.L5):
    """建 orchestrator，registry loader 注入單一 capability；D3 writer 注入 mock 避免真 DB。"""
    reg = REG.L2CapabilityRegistry(capabilities={cap.capability_id: cap})
    o = ORCH.L2AdvisoryOrchestrator(
        cost_tracker=tracker or _FakeTracker(),
        registry_loader=lambda: reg,
        current_tier=tier,
        posture=posture,
    )
    return o


@pytest.fixture(autouse=True)
def _mock_ledger(monkeypatch):
    """所有 orchestrator 測試：D3 writer 注入 mock（gate-seam 記錄不打真 DB）。"""
    fake = MagicMock()
    fake.record_gate_seam.return_value = {"ok": True}
    fake.record_l2_call.return_value = {"ok": True}
    monkeypatch.setattr(ORCH, "_get_l2_ledger_writer", lambda: fake)
    return fake


class TestAdmission:
    def test_unknown_capability_failclosed(self):
        o = _orch_with(_make_cap(capability_id="present", lane="research"))
        r = o.dispatch(capability_id="absent")
        assert r.admitted is False
        assert r.admission_reason == "unknown_capability"

    def test_disabled_capability_failclosed(self):
        cap = _make_cap(capability_id="c", enabled=False, lane="research")
        o = _orch_with(cap)
        r = o.dispatch(capability_id="c")
        assert r.admitted is False
        assert r.admission_reason == "capability_disabled"

    def test_admit_neutral_routes_to_neutral_sink(self):
        cap = _make_cap(capability_id="c", lane="research")
        o = _orch_with(cap)
        r = o.dispatch(capability_id="c", now=1000.0)
        assert r.admitted is True
        assert r.routed_to == "neutral_sink"

    def test_dedup_drops_repeat_in_window(self):
        """同 dedup_key 在窗口內第二次 → trigger_deduped（無重複放行）。"""
        trig = REG.L2CapabilityTrigger(kind="event", spec="s", debounce_secs=0)
        cap = _make_cap(capability_id="c", lane="research", trigger=trig)
        o = _orch_with(cap)
        r1 = o.dispatch(capability_id="c", coarse_subject="BTC", now=1000.0)
        r2 = o.dispatch(capability_id="c", coarse_subject="BTC", now=1000.5)
        assert r1.admitted is True
        assert r2.admitted is False
        assert r2.admission_reason == "trigger_deduped"

    def test_debounce_first_fire_deferred(self):
        """debounce_secs>0：首次見 burst → debounced（trailing-edge）。"""
        trig = REG.L2CapabilityTrigger(kind="event", spec="s", debounce_secs=900)
        cap = _make_cap(capability_id="c", lane="research", trigger=trig)
        o = _orch_with(cap)
        r = o.dispatch(capability_id="c", coarse_subject="BTC", now=1000.0)
        assert r.admitted is False
        assert r.admission_reason == "debounced"

    def test_storm_cannot_blow_budget_even_debounce_off(self):
        """storm-control 鐵律：debounce OFF，預算耗盡時 budget 硬閘擋住（不超 DOC-08）。"""
        trig = REG.L2CapabilityTrigger(kind="event", spec="s", debounce_secs=0)
        cap = _make_cap(capability_id="c", lane="research", trigger=trig)
        tracker = _FakeTracker(allowed=False, remaining=0.0)  # 預算已耗盡
        o = _orch_with(cap, tracker=tracker)
        # 即便每次都用新 subject（繞過 dedup），budget 硬閘仍擋。
        for i in range(20):
            r = o.dispatch(capability_id="c", coarse_subject=f"sub{i}", now=1000.0 + i)
            assert r.admitted is False
            assert r.admission_reason == "budget_exceeded"

    def test_tier_locked_when_insufficient(self):
        cap = _make_cap(capability_id="c", lane="research", min_tier="L4")
        o = _orch_with(cap, tier=LearningTier.L1)
        r = o.dispatch(capability_id="c", now=1000.0)
        assert r.admitted is False
        assert r.admission_reason == "tier_locked"

    def test_expand_lane_routed_manual_not_auto(self):
        """expand lane（demo_stage1）→ admission MANUAL → manual_inbox（永不 auto-call）。"""
        cap = _make_cap(capability_id="c", lane="demo_stage1")
        o = _orch_with(cap, posture="Standard", tier=LearningTier.L5)
        r = o.dispatch(capability_id="c", now=1000.0)
        assert r.admitted is False
        assert r.admission_reason == "manual"
        assert r.routed_to == "manual_inbox"

    def test_budget_gate_is_called(self):
        """budget gate 確被呼（admission stage 4 真接 check_daily_budget）。"""
        cap = _make_cap(capability_id="c", lane="research")
        tracker = _FakeTracker(allowed=True, remaining=1.5)
        o = _orch_with(cap, tracker=tracker)
        o.dispatch(capability_id="c", now=1000.0)
        assert tracker.calls >= 1

    def test_admission_records_gate_seam(self, _mock_ledger):
        """admission 決策落 gate-seam（trigger_decision reason）——可達性驗。"""
        cap = _make_cap(capability_id="c", lane="research")
        o = _orch_with(cap)
        o.dispatch(capability_id="c", now=1000.0)
        assert _mock_ledger.record_gate_seam.called
        kwargs = _mock_ledger.record_gate_seam.call_args.kwargs
        assert kwargs["gate_id"] == "admission"
        assert "trigger_decision" in kwargs["details"]

    def test_per_cap_ceiling_independent_of_global_budget(self):
        """HIGH-1：per-cap 日上限獨立於全域 budget。

        cap_daily=$0.50（小）而全域 remaining=$2.00（大）→ 該 cap 累計花到 $0.50 後，
        即便全域仍寬鬆，該 cap 仍被擋（per_capability_daily_ceiling）。這正是舊 no-op
        分支（re-read 全域 remaining）宣稱卻不存在的保證。
        """
        budget = REG.L2CapabilityBudget(per_call_usd_cap=0.25, daily_usd_cap=0.5)
        cap = _make_cap(capability_id="c", lane="research", budget=budget)
        tracker = _FakeTracker(allowed=True, remaining=2.0)  # 全域寬鬆
        o = _orch_with(cap, tracker=tracker)

        # 花費 0 → 仍可放行（全域 + per-cap 皆未達）。
        r0 = o.dispatch(capability_id="c", coarse_subject="A", now=1000.0)
        assert r0.admitted is True

        # P3 executor 累計該 cap 當日花費到 cap_daily（用 dispatch 同日 ts）。
        o.record_capability_spend("c", 0.5, now=1000.0)

        # per-cap 已達 → 即便全域 remaining=$2.00 仍寬鬆，該 cap 被擋（獨立於全域）。
        r1 = o.dispatch(capability_id="c", coarse_subject="B", now=1001.0)
        assert r1.admitted is False
        assert r1.admission_reason == "budget_exceeded"
        # 確認是 per-cap ceiling（非全域）——全域 allowed=True 證明非全域觸發。
        decision = o._admit(cap, coarse_subject="C", ts=1002.0)
        assert decision.details.get("reason") == "per_capability_daily_ceiling"
        assert decision.details.get("cap_daily_usd") == 0.5

    def test_per_cap_spend_rolls_over_next_utc_day(self):
        """per-cap 累計按 UTC-day 歸桶：跨日後該 cap 重新可放行（新 day_key 無紀錄）。"""
        budget = REG.L2CapabilityBudget(daily_usd_cap=0.5)
        cap = _make_cap(capability_id="c", lane="research", budget=budget)
        o = _orch_with(cap, tracker=_FakeTracker(allowed=True, remaining=2.0))
        # day1 花滿 → 擋。
        day1 = 1_700_000_000.0  # 某 UTC 日
        o.record_capability_spend("c", 0.5, now=day1)
        d1 = o._admit(cap, coarse_subject="X", ts=day1 + 10)
        assert d1.details.get("reason") == "per_capability_daily_ceiling"
        # +1 天 → 新 UTC day_key，累計歸零 → 放行。
        d2 = o._admit(cap, coarse_subject="Y", ts=day1 + 86_400 + 100)
        assert d2.admitted is True

    def test_per_cap_record_spend_nonpositive_is_noop(self):
        """record_capability_spend usd<=0 視為 no-op（不污染 accumulator）。"""
        budget = REG.L2CapabilityBudget(daily_usd_cap=0.5)
        cap = _make_cap(capability_id="c", lane="research", budget=budget)
        o = _orch_with(cap, tracker=_FakeTracker(allowed=True, remaining=2.0))
        o.record_capability_spend("c", 0.0, now=1000.0)
        o.record_capability_spend("c", -5.0, now=1000.0)
        # 仍可放行（accumulator 未被污染）。
        assert o._cap_spend_today("c", 1000.0) == 0.0
        assert o._admit(cap, coarse_subject="Z", ts=1000.0).admitted is True

    def test_per_cap_no_budget_stanza_skips_ceiling(self):
        """無 budget stanza（cap_daily=0）→ per-cap 閘略過（只受全域 DOC-08 約束）。"""
        cap = _make_cap(capability_id="c", lane="research")  # 無 budget
        o = _orch_with(cap, tracker=_FakeTracker(allowed=True, remaining=2.0))
        # 即便「假裝」記了花費，cap_daily=0 → per-cap 分支不進（cap_daily>0 才檢查）。
        o.record_capability_spend("c", 99.0, now=1000.0)
        assert o._admit(cap, coarse_subject="W", ts=1000.0).admitted is True

    def test_admission_window_uses_lock(self):
        """MED-2：admission 臨界區（dedup read-modify-write）持 self._lock，且鎖為 RLock（重入安全）。

        _thread.RLock.__enter__ 唯讀無法 monkeypatch；改用計數 proxy 替換 o._lock，包 acquire/
        __enter__ 計數，證 _admit 進過臨界區。RLock 語義（重入）由 proxy 內含 RLock 提供，使
        _admit 內呼 _cap_spend_today 重入取鎖不自鎖。
        """
        import threading as _th

        class _CountingRLock:
            """delegates 到真 RLock，計數 __enter__（admission 進臨界區的證據）。"""

            def __init__(self):
                self._rl = _th.RLock()
                self.enter_count = 0

            def __enter__(self):
                self.enter_count += 1
                return self._rl.__enter__()

            def __exit__(self, *a):
                return self._rl.__exit__(*a)

            def acquire(self, *a, **k):
                return self._rl.acquire(*a, **k)

            def release(self):
                return self._rl.release()

        cap = _make_cap(capability_id="c", lane="research")
        o = _orch_with(cap)
        # 生產碼用 RLock（非 non-reentrant Lock）：admission 內 _cap_spend_today 重入取鎖。
        assert isinstance(o._lock, type(_th.RLock())), "admission lock 必為 RLock（重入安全）"

        proxy = _CountingRLock()
        o._lock = proxy  # 替換成計數 proxy（RLock 語義保留）
        o._admit(cap, coarse_subject="X", ts=1000.0)
        # _admit 進臨界區（≥1）；其內 _cap_spend_today 重入（≥2，無 budget 故不觸發，仍進 admission）。
        assert proxy.enter_count >= 1, "_admit 必進 self._lock 臨界區（MED-2）"

    def test_concurrent_same_dedup_key_only_one_admitted(self):
        """MED-2 行為驗：多執行緒同 dedup_key 並發 → 至多一個 admitted（dedup 不失效）。

        無鎖時兩執行緒都讀 last_served_ts=None 都 admit；有鎖時 read-modify-write 原子化，
        只有一個贏。用 barrier 逼近真並發。
        """
        import threading as _th

        trig = REG.L2CapabilityTrigger(kind="event", spec="s", debounce_secs=0)
        cap = _make_cap(capability_id="c", lane="research", trigger=trig)
        o = _orch_with(cap)

        n_threads = 16
        barrier = _th.Barrier(n_threads)
        results: list[bool] = []
        results_lock = _th.Lock()

        def _worker():
            barrier.wait()  # 同步起跑逼近真並發
            d = o._admit(cap, coarse_subject="BTC", ts=1000.0)
            with results_lock:
                results.append(d.admitted)

        threads = [_th.Thread(target=_worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 同 dedup_key + 同窗口 → 至多一個贏（其餘 trigger_deduped）。
        assert sum(1 for r in results if r) == 1, \
            f"並發同 dedup_key 應僅 1 admitted（dedup 原子），實得 {sum(results)}"

    def test_mutation_bite_per_cap_ceiling_uses_accumulator_not_global(self):
        """mutation 驗（HIGH-1）：per-cap 閘讀 per-cap accumulator，非全域 remaining。

        構造：全域 remaining 大（allowed=True）+ cap 花費已達 cap_daily。正確實作（讀
        accumulator）→ 擋；舊 no-op（讀全域 remaining>0）→ 放行。此測試斷言「擋」，故
        若回退成讀全域 remaining 會紅（bite）。
        """
        budget = REG.L2CapabilityBudget(daily_usd_cap=0.5)
        cap = _make_cap(capability_id="c", lane="research", budget=budget)
        o = _orch_with(cap, tracker=_FakeTracker(allowed=True, remaining=2.0))
        o.record_capability_spend("c", 0.5, now=1000.0)
        d = o._admit(cap, coarse_subject="K", ts=1000.0)
        assert d.admitted is False
        assert d.details.get("reason") == "per_capability_daily_ceiling"


# ═══════════════════════════════════════════════════════════════════════════════
# Fail-safe SM — §H（每態減 L2 能力；worst=NO_ADVICE；0 live-enabling write）
# ═══════════════════════════════════════════════════════════════════════════════


class TestFailSafe:
    def test_healthy_on_ok(self):
        o = ORCH.L2AdvisoryOrchestrator()
        assert o.report_call_outcome(ok=True) == ORCH.FailSafeState.HEALTHY

    def test_retry_then_degrade_then_no_advice(self):
        """連續失敗：RETRY → DEGRADE_OLLAMA（ollama 可用）→ NO_ADVICE（ollama 不可用）。"""
        o = ORCH.L2AdvisoryOrchestrator(max_retries=1)
        s1 = o.report_call_outcome(ok=False, ollama_available=True)
        assert s1 == ORCH.FailSafeState.RETRY
        s2 = o.report_call_outcome(ok=False, ollama_available=True)
        assert s2 == ORCH.FailSafeState.DEGRADE_OLLAMA
        s3 = o.report_call_outcome(ok=False, ollama_available=False)
        assert s3 == ORCH.FailSafeState.NO_ADVICE

    def test_escalates_to_tripped_then_global_conservative(self):
        o = ORCH.L2AdvisoryOrchestrator(max_retries=1)
        for _ in range(12):
            s = o.report_call_outcome(ok=False, ollama_available=False)
        assert s == ORCH.FailSafeState.GLOBAL_CONSERVATIVE

    def test_ollama_up_persistent_failure_still_escalates(self):
        """MED-1：ollama 持續可用但呼叫持續失敗 → 仍須跨閾值升級至 TRIPPED/GLOBAL_CONSERVATIVE。

        舊 bug：`elif ollama_available: DEGRADE_OLLAMA` 在計數閾值之前 → ollama-up 永卡
        DEGRADE_OLLAMA，到不了 TRIPPED（違 design §H systemic escalation）。修後：escalation
        與 ollama_available 解耦，計數跨 5→TRIPPED、跨 10→GLOBAL_CONSERVATIVE，即便 ollama up。
        """
        o = ORCH.L2AdvisoryOrchestrator(max_retries=1)
        states = []
        for _ in range(50):  # 50 連敗，ollama 全程 up
            states.append(o.report_call_outcome(ok=False, ollama_available=True))
        # 不可永卡 DEGRADE_OLLAMA。
        assert states[-1] != ORCH.FailSafeState.DEGRADE_OLLAMA, \
            "ollama-up 持續失敗不得永卡 DEGRADE_OLLAMA（MED-1）"
        # 50 連敗（>10）→ GLOBAL_CONSERVATIVE。
        assert states[-1] == ORCH.FailSafeState.GLOBAL_CONSERVATIVE
        # 過程確曾經過 DEGRADE_OLLAMA（中間階 ollama-up floor）再升級。
        assert ORCH.FailSafeState.DEGRADE_OLLAMA in states
        assert ORCH.FailSafeState.TRIPPED in states

    def test_ollama_up_reaches_tripped_band(self):
        """MED-1 細節：ollama-up 時，連續失敗計數進 [5,10) 應為 TRIPPED（非 DEGRADE_OLLAMA）。"""
        o = ORCH.L2AdvisoryOrchestrator(max_retries=1)
        s = None
        for _ in range(6):  # cf=6 ∈ [5,10)
            s = o.report_call_outcome(ok=False, ollama_available=True)
        assert s == ORCH.FailSafeState.TRIPPED, "cf∈[5,10) ollama-up 應 TRIPPED（escalation 解耦）"

    def test_ok_resets_to_healthy(self):
        o = ORCH.L2AdvisoryOrchestrator(max_retries=1)
        o.report_call_outcome(ok=False, ollama_available=False)
        o.report_call_outcome(ok=False, ollama_available=False)
        assert o.report_call_outcome(ok=True) == ORCH.FailSafeState.HEALTHY

    def test_no_advice_state_drops_dispatch(self, _mock_ledger):
        """NO_ADVICE 態：admitted 後仍 drop（減 L2 能力，走 baseline，不發 advice）。"""
        cap = _make_cap(capability_id="c", lane="research")
        o = _orch_with(cap)
        # 強制進 NO_ADVICE
        for _ in range(4):
            o.report_call_outcome(ok=False, ollama_available=False)
        assert o._fail_safe == ORCH.FailSafeState.NO_ADVICE
        r = o.dispatch(capability_id="c", now=1000.0)
        assert r.routed_to == "dropped"

    def test_fail_safe_sm_source_no_live_enabling_write(self):
        """grep：report_call_outcome 真碼不寫任何 live-enabling state（§H 鐵律；剝 docstring）。"""
        src = inspect.getsource(ORCH.L2AdvisoryOrchestrator.report_call_outcome)
        # 剝首個 docstring（解釋鐵律時會提及這些字）。
        code = src
        if '"""' in code:
            first = code.index('"""')
            second = code.index('"""', first + 3)
            code = code[:first] + code[second + 3:]
        for forbidden in (
            "live_execution_allowed",
            "OPENCLAW_ALLOW_MAINNET",
            "promote_tier",
            "acquire_lease",
        ):
            assert forbidden not in code


# ═══════════════════════════════════════════════════════════════════════════════
# Contract registry — §D（versioned，manual 零回歸）
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegistryFailSoftReadPath:
    """E2-LOW-1：read-path（status / _registry_obj）遇 malformed TOML 須 fail-soft（不 raise/500）。"""

    def test_cold_cache_malformed_toml_status_does_not_raise(self):
        """cold-cache 載入 raise L2RegistryLoadError → status() 不冒泡（回 degraded），不 500。"""
        def _bad_loader():
            raise REG.L2RegistryLoadError("TOML 解析失敗（l2_capability_registry.toml）：boom")

        o = ORCH.L2AdvisoryOrchestrator(registry_loader=_bad_loader)
        # 不應 raise（舊行為：冒泡成 GET 500）。
        st = o.status()
        assert st["registry_degraded"] is True
        assert st["registry_degraded_reason"] == "registry_load_rejected"
        # fail-closed：降級時無 enabled capability（不誤放行 advisory）。
        assert st["enabled_capabilities"] == []
        assert st["registered_capabilities"] == []

    def test_failsoft_retains_last_good_after_bad_reload(self):
        """先成功載入（last-good）→ reload 後新 TOML 壞 → read-path 退 last-good（非空）+ degraded。"""
        good = REG.L2CapabilityRegistry(
            capabilities={"c": _make_cap(capability_id="c", lane="research")}
        )
        state = {"fail": False}

        def _loader():
            if state["fail"]:
                raise REG.L2RegistryLoadError("malformed")
            return good

        o = ORCH.L2AdvisoryOrchestrator(registry_loader=_loader)
        st1 = o.status()
        assert st1["registry_degraded"] is False
        assert st1["registered_capabilities"] == ["c"]

        # operator reload，但新 TOML 壞掉。
        state["fail"] = True
        o.reload_registry()
        st2 = o.status()
        # 退 last-good（保留 c）+ 標記 degraded。
        assert st2["registry_degraded"] is True
        assert st2["registered_capabilities"] == ["c"]

    def test_failsoft_recovers_when_toml_fixed(self):
        """壞 → 修好 → reload → degraded 清除。"""
        good = REG.L2CapabilityRegistry(
            capabilities={"c": _make_cap(capability_id="c", lane="research")}
        )
        state = {"fail": True}

        def _loader():
            if state["fail"]:
                raise REG.L2RegistryLoadError("malformed")
            return good

        o = ORCH.L2AdvisoryOrchestrator(registry_loader=_loader)
        assert o.status()["registry_degraded"] is True  # cold-cache 壞 → 空 + degraded
        state["fail"] = False
        o.reload_registry()
        st = o.status()
        assert st["registry_degraded"] is False
        assert st["registered_capabilities"] == ["c"]


class TestRegistryLoaderPathLeak:
    """E3-LOW-1：loader error 不得嵌絕對路徑（繞過 _LEAK_PATTERN 洩 /home/ncyu）。"""

    def test_parse_error_message_uses_basename_not_abspath(self, tmp_path):
        """malformed TOML 的 L2RegistryLoadError 只含 basename，不含 resolved 絕對路徑。"""
        bad = tmp_path / "l2_capability_registry.toml"
        bad.write_text("this is = = not valid toml ===\n[[[\n", encoding="utf-8")
        with pytest.raises(REG.L2RegistryLoadError) as ei:
            REG.load_capability_registry(bad)
        msg = str(ei.value)
        # 只含 basename。
        assert "l2_capability_registry.toml" in msg
        # 不含 tmp_path 的絕對前綴（resolved path）。
        assert str(tmp_path) not in msg, f"error 不得含絕對路徑：{msg!r}"
        # 防 /home/<user> /Users/<user> runtime 路徑洩漏（CLAUDE §六）。
        assert "/home/" not in msg
        assert "/Users/" not in msg

    def test_loader_source_basenames_path_in_error(self):
        """grep：loader 真碼用 p.name（basename）而非裸 p 構造解析錯誤訊息。"""
        src = inspect.getsource(REG.load_capability_registry)
        assert "p.name" in src, "loader 須以 p.name basename 化路徑（E3-LOW-1）"


class TestContractRegistry:
    def test_manual_resolves_to_existing_versions(self):
        """manual capability 解析 = 既有 l2_contract.v1 / l2_schema.v1（零回歸）。"""
        cv, sv = CONTRACTS.resolve_contract_versions(capability_id="l2.manual_reasoning")
        assert cv == "l2_contract.v1"
        assert sv == "l2_schema.v1"

    def test_unknown_capability_falls_back_to_constants(self):
        """未知 capability ref → fallback 既有常數（D3 仍寫得出）。"""
        cv, sv = CONTRACTS.resolve_contract_versions(capability_id="nonexistent")
        assert cv == "l2_contract.v1"
        assert sv == "l2_schema.v1"

    def test_prompt_contract_template_not_model_generated(self):
        """種子 contract 的 template 是 checked-in 常數（manual 為空 = 用既有 SYSTEM_PROMPT）。"""
        pc = CONTRACTS.get_prompt_contract("l2.manual_reasoning.v1")
        assert pc is not None
        assert pc.contract_ver == "l2_contract.v1"
        # frozen：契約不可變（同 ref 永得同模板）
        with pytest.raises(Exception):
            pc.contract_ver = "mutated"


class TestEngineWiringDeltaReachable:
    """P2 wiring delta（PA §A.2）reachability：layer2_engine._record_l2_call_to_ledger 真接
    contract registry，且 manual capability 解析回既有 l2_contract.v1（證明非死碼 + 零回歸）。"""

    def test_engine_record_uses_registry_resolved_contract_ver(self, monkeypatch):
        from app.layer2_engine import Layer2Engine
        from app.layer2_types import Layer2Session
        from app import provider_client as pc

        engine = Layer2Engine(cost_tracker=MagicMock())
        session = Layer2Session(trigger="manual")
        response = pc.L2Response(text="r", input_tokens=1, output_tokens=1)
        captured = {}

        class _FakeWriter:
            def record_l2_call(self, **kwargs):
                captured.update(kwargs)
                return {"ok": True}

        monkeypatch.setattr(
            "app.layer2_engine._get_l2_ledger_writer", lambda: _FakeWriter()
        )
        engine._record_l2_call_to_ledger(
            session=session,
            system_prompt="SYS",
            messages=[{"role": "user", "content": "hi"}],
            response=response,
            eff_model="haiku",
            latency_ms=None,
        )
        # wiring delta：contract_ver/schema_ver 來自 registry 解析，值 = 既有常數（零回歸）。
        assert captured["contract_ver"] == "l2_contract.v1"
        assert captured["schema_ver"] == "l2_schema.v1"


# ═══════════════════════════════════════════════════════════════════════════════
# re-E2 MED-1 — cap_daily_spend 有界（prune 非今日桶，防無界增長）
# ═══════════════════════════════════════════════════════════════════════════════


class TestPerCapSpendBounded:
    """re-E2 MED-1：record_capability_spend 清非今日桶 → cap_daily_spend 有界。

    舊行為：每日每 cap 一永久 key，線性無界（P3 接 executor 即活、無 healthcheck 可察）。
    修後：寫入時 prune 非今日桶，dict 任何時刻只含「今日」key（≤ cap 數）。
    """

    def test_spend_dict_bounded_across_many_days(self):
        """跨多日 record 後，cap_daily_spend 只剩今日的 key（有界 = cap 數，非天數×cap 數）。"""
        budget = REG.L2CapabilityBudget(daily_usd_cap=0.5)
        cap = _make_cap(capability_id="c", lane="research", budget=budget)
        o = _orch_with(cap, tracker=_FakeTracker(allowed=True, remaining=2.0))

        # 跨 30 個不同 UTC 日各記一筆（同一 cap）。
        day0 = 1_700_000_000.0
        for d in range(30):
            o.record_capability_spend("c", 0.1, now=day0 + d * 86_400)

        spend = o._admission.cap_daily_spend
        # 有界：只剩最後一天的 key（非 30 個）。
        assert len(spend) == 1, f"跨 30 日後應只剩 1 key（今日），實得 {len(spend)}"
        last_day = ORCH._utc_day(day0 + 29 * 86_400)
        assert list(spend.keys()) == [("c", last_day)]

    def test_spend_dict_bounded_multi_cap_single_day(self):
        """同一日多 cap：bound = cap 數（每 cap 一今日 key），不洩漏。"""
        o = _orch_with(_make_cap(capability_id="c", lane="research"))
        now = 1_700_000_000.0
        for i in range(20):
            o.record_capability_spend(f"cap{i}", 0.1, now=now)
        spend = o._admission.cap_daily_spend
        # 20 cap 同日 → 20 key（皆今日）；無跨日洩漏。
        assert len(spend) == 20
        today = ORCH._utc_day(now)
        assert all(day == today for (_cid, day) in spend)

    def test_today_spend_survives_prune(self):
        """prune 不誤刪今日桶：寫第二筆（同日）累加而非歸零，且閘仍讀得到。"""
        budget = REG.L2CapabilityBudget(daily_usd_cap=0.5)
        cap = _make_cap(capability_id="c", lane="research", budget=budget)
        o = _orch_with(cap, tracker=_FakeTracker(allowed=True, remaining=2.0))
        now = 1_700_000_000.0
        o.record_capability_spend("c", 0.2, now=now)
        o.record_capability_spend("c", 0.2, now=now + 100)  # 同日第二筆
        # 累加（0.4），非被自身 prune 清掉。
        assert abs(o._cap_spend_today("c", now) - 0.4) < 1e-9

    def test_prune_drops_only_stale_keeps_today_when_mixed(self):
        """昨日桶 + 今日寫入 → 昨日被 prune，今日保留（直接驗 prune 行為）。"""
        o = _orch_with(_make_cap(capability_id="c", lane="research"))
        today = 1_700_086_400.0
        yesterday = today - 86_400
        # 手動植入昨日桶（模擬跨日後遺留）。
        y_key = ("c", ORCH._utc_day(yesterday))
        o._admission.cap_daily_spend[y_key] = 0.3
        # 今日寫入 → 觸發 prune。
        o.record_capability_spend("c", 0.1, now=today)
        spend = o._admission.cap_daily_spend
        assert y_key not in spend, "昨日桶應被 prune"
        assert ("c", ORCH._utc_day(today)) in spend, "今日桶應保留"
        assert len(spend) == 1

    def test_mutation_bite_without_prune_grows_unbounded(self):
        """mutation 驗：若 record 不呼 _prune_stale_spend，跨日會無界增長（本測試斷言有界）。

        構造：跨多日 record。正確實作（prune）→ len==1；移除 prune → len==N（紅）。此測試
        斷言 len==1，故回退（拿掉 prune 呼叫）會紅 = bite。
        """
        o = _orch_with(_make_cap(capability_id="c", lane="research"))
        day0 = 1_700_000_000.0
        for d in range(10):
            o.record_capability_spend("c", 0.05, now=day0 + d * 86_400)
        # 有界（prune 生效）：跨 10 日仍只 1 key。
        assert len(o._admission.cap_daily_spend) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# re-E2 LOW-1 — registry fail-soft 降級語義（cold-cache 退空 vs warm 退 last-good）
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegistryFailSoftSemantics:
    """re-E2 LOW-1：修正「降級必空」overclaim。warm last-good 退回保留已驗證 enabled cap。

    docstring 舊稱「降級時 enabled_capabilities 為空，不會誤放行」——僅 cold-cache 成立。
    warm 退 last-good（已通過全 loader reject 的已驗證 config）時 enabled cap 仍保留、dispatch
    仍可 admit。此為合理 subtraction-only 降級（不切換壞 TOML、不引入新 cap），非放行壞 config。
    """

    def test_cold_cache_degraded_is_empty_failclosed(self):
        """cold-cache 無 last-good → 退空 registry：enabled_capabilities 為空（真 fail-closed）。"""
        def _bad_loader():
            raise REG.L2RegistryLoadError("malformed cold")

        o = ORCH.L2AdvisoryOrchestrator(registry_loader=_bad_loader)
        reg = o._registry_obj()
        assert o._registry_degraded is True
        assert reg.enabled_capabilities() == []  # cold-cache 退空 = 真 fail-closed

    def test_warm_degraded_retains_validated_enabled_caps(self):
        """warm last-good 退回 → 保留先前已驗證的 enabled capability（非空，dispatch 仍 admit）。

        這正是 docstring 舊「降級必空」overclaim 被 LOW-1 修正之處：warm 降級保留已驗證 config。
        """
        good = REG.L2CapabilityRegistry(
            capabilities={"c": _make_cap(capability_id="c", enabled=True, lane="research")}
        )
        state = {"fail": False}

        def _loader():
            if state["fail"]:
                raise REG.L2RegistryLoadError("malformed warm")
            return good

        o = ORCH.L2AdvisoryOrchestrator(
            cost_tracker=_FakeTracker(allowed=True, remaining=2.0),
            registry_loader=_loader,
        )
        # 首次成功載入（warm up last-good）。
        reg1 = o._registry_obj()
        assert [c.capability_id for c in reg1.enabled_capabilities()] == ["c"]

        # operator reload，但新 TOML 壞 → 退 last-good（保留已驗證 enabled cap）。
        state["fail"] = True
        o.reload_registry()
        reg2 = o._registry_obj()
        assert o._registry_degraded is True
        # **非空**：warm 降級保留已驗證 enabled cap（修正「降級必空」overclaim）。
        assert [c.capability_id for c in reg2.enabled_capabilities()] == ["c"]
        # 且 dispatch 仍可 admit 該已驗證 cap（last-good 是已通過 reject 的 config，合理放行）。
        r = o.dispatch(capability_id="c", coarse_subject="X", now=1000.0)
        assert r.admitted is True

    def test_docstring_distinguishes_cold_vs_warm(self):
        """grep：_registry_obj docstring 區分 cold-cache 退空 vs warm 退 last-good（無「降級必空」斷言）。"""
        doc = inspect.getsource(ORCH.L2AdvisoryOrchestrator._registry_obj)
        assert "cold-cache" in doc and "last-good" in doc
        # 不再保留 overclaim 句「降級時 enabled_capabilities 為空，不會誤放行任何 advisory」。
        assert "降級時 enabled_capabilities\n        為空" not in doc
        assert "advisory subtraction-only" in doc  # 明確標 warm 是 subtraction-only 降級


# ═══════════════════════════════════════════════════════════════════════════════
# re-E2 fold-in — /cost/reset + /cost/pricing operator-scope（P2 budget-integrity）
# ═══════════════════════════════════════════════════════════════════════════════


def _viewer_actor():
    """已認證但僅 viewer：有 read scope、無 operator 角色、無 ai_budget:write。"""
    from types import SimpleNamespace
    return SimpleNamespace(actor_id="viewer", roles={"viewer"}, scopes={"state:read"})


def _operator_actor():
    """operator + ai_budget:write scope（合法 WRITE 身分）。"""
    from types import SimpleNamespace
    return SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"ai_budget:write"})


class TestCostMutationRoutesOperatorScoped:
    """re-E2 fold-in：/cost/reset 與 /cost/pricing 是 operator-scope WRITE（鏡像 /registry/reload）。

    為什麼是 budget-integrity 命門：reset_today_costs 歸零 DOC-08 $2/day counter ＝ 繞過 P2
    admission storm-control 剛驗的 $2/day 硬閘（cap-bypass）。先前只有 Depends(current_actor)，
    任何已認證 viewer 可 reset。auth matrix：viewer→403、operator+scope→允許。直接呼 handler
    驗已接線的 gate（不需 running app；viewer 在 gate 即 403，operator 通過後 mock tracker）。
    """

    def test_cost_reset_rejects_viewer(self):
        """viewer 打 /cost/reset → 403（require_scope_and_operator 在 state 變更前攔）。"""
        import asyncio
        from fastapi import HTTPException
        from app import layer2_routes as LR

        with pytest.raises(HTTPException) as ei:
            asyncio.run(LR.reset_today_costs(actor=_viewer_actor()))
        assert ei.value.status_code == 403

    def test_cost_reset_allows_operator(self, monkeypatch):
        """operator+scope 打 /cost/reset → 通過 gate（state 變更執行）。"""
        import asyncio
        from app import layer2_routes as LR

        fake = MagicMock()
        fake.reset_today_costs.return_value = {"total_usd": 0.0}
        monkeypatch.setattr(LR, "_get_cost_tracker", lambda: fake)
        out = asyncio.run(LR.reset_today_costs(actor=_operator_actor()))
        # gate 通過 → 真呼 reset（cap-bypass 風險點受 operator-scope 保護）。
        assert fake.reset_today_costs.called
        # 回應走 _layer2_response envelope（payload 在 ["data"]）。
        assert out["data"]["cleared"] == {"total_usd": 0.0}

    def test_cost_pricing_rejects_viewer(self):
        """viewer 打 /cost/pricing（POST 更新）→ 403。"""
        import asyncio
        from fastapi import HTTPException
        from app import layer2_routes as LR

        req = LR.PricingUpdateRequest(perplexity_per_search=0.01)
        with pytest.raises(HTTPException) as ei:
            asyncio.run(LR.update_pricing(req=req, actor=_viewer_actor()))
        assert ei.value.status_code == 403

    def test_cost_pricing_allows_operator(self, monkeypatch):
        """operator+scope 打 /cost/pricing → 通過 gate。"""
        import asyncio
        from app import layer2_routes as LR

        fake = MagicMock()
        fake.update_pricing.return_value = MagicMock(to_dict=lambda: {"ok": True})
        monkeypatch.setattr(LR, "_get_cost_tracker", lambda: fake)
        req = LR.PricingUpdateRequest(perplexity_per_search=0.01)
        out = asyncio.run(LR.update_pricing(req=req, actor=_operator_actor()))
        assert fake.update_pricing.called
        assert out["data"]["pricing"] == {"ok": True}

    def test_operator_missing_budget_scope_rejected(self):
        """operator 角色但缺 ai_budget:write scope → 403（scope gate 亦攔）。"""
        import asyncio
        from types import SimpleNamespace
        from fastapi import HTTPException
        from app import layer2_routes as LR

        op_no_scope = SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"state:read"})
        with pytest.raises(HTTPException) as ei:
            asyncio.run(LR.reset_today_costs(actor=op_no_scope))
        assert ei.value.status_code == 403

    def test_handlers_source_calls_scope_gate_before_mutation(self):
        """grep（鏡像 test_static_high_risk_posts_use_scope_gates）：兩 handler 真碼在任何
        tracker mutation 之前呼 require_scope_and_operator(ai_budget:write)。"""
        from app import layer2_routes as LR

        for fn in (LR.reset_today_costs, LR.update_pricing):
            src = inspect.getsource(fn)
            assert 'base.require_scope_and_operator(actor, "ai_budget:write")' in src, \
                f"{fn.__name__} 須呼 operator-scope gate"
            idx_gate = src.index("require_scope_and_operator")
            idx_tracker = src.index("_get_cost_tracker")
            assert idx_gate < idx_tracker, \
                f"{fn.__name__}：gate 必在 _get_cost_tracker（state 取用）之前"
