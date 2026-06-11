"""
MODULE_NOTE
模塊用途：
  L2 Advisory Mesh 確定性 out-of-bound guard（PA P2 設計 §E）。在「proposal 形成之前」跑，
  catch 幻覺參數（leverage 50x / size 80% / 負成本）而**無需人眼**。verdict ∈
  {pass, clamp, reject}，由 Orchestrator 寫進既有 agent.l2_calls.guard_verdict 欄（V134）。

  防禦縱深分工：本 guard 抓「形」（幻覺參數 shape）；確定性 math gate（P3/P4）抓「實」
  （alpha 是否真）。guard 是 model 輸出「成為 proposal 之前」的便宜結構網。

主要類/函數：
  - GuardResult：dataclass（verdict / clamped_output / kinds_hit）。
  - guard_output(parsed_output, *, guard_ref, context):純確定性函數，跑通用 clause。
  - _guard_ml_advisory_v1(parsed_output, *, context):P3a capability-specific clauses
    （M3 source_class typing / regime_caveat when bull-only / axes-subset）。
  - get_guard(guard_ref):callable registry 查詢（P2 是 ref echo；P3 回 callable）。
  - run_guard(parsed_output, *, guard_ref, context):依 guard_ref 路由到對應 guard callable。

依賴：
  - 無 model、無 DB；純函數 + 確定性 bounds。
  - l2_prompt_contract_registry 的 M3 source_class 常數（ML_ADVISORY_LEAK_SOURCE_CLASSES /
    ML_ADVISORY_LEAKFREE_SOURCE_CLASSES）+ per-mode 必填欄（單一 source，不複製字面集合）。

硬邊界：
  - 確定性：guard 內**無 model 呼叫**（CC/E2 grep target）；同輸入永得同 verdict。
  - 在 record_l2_call 寫 parsed_output「之前」跑；reject ⇒ proposal「永不」route 給 applier
    （logged-and-dropped）。
  - clamp ⇒ clamped_output 才是後續使用的值（非原始幻覺值）。
  - 純 guard：無 order surface、無 lease、無 promote。
  - guard 抓「形」（M3 typing / regime_caveat 缺漏 / 捏造軸），math gate 抓「實」；P3a 無 alpha
    math gate（diagnose/interpret 斷言無 alpha），故 guard 的 M3 typing 是 P3a 主要 gate。
  - GUARD_REGISTRY 是 module-level 不可變 dict（frozen at import；stateless，無 mutable singleton，
    對齊 singleton-registry.md:392「l2_out_of_bound_guard 純確定性函數，無 singleton」）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

logger = logging.getLogger("l2_out_of_bound_guard")

GuardVerdict = Literal["pass", "clamp", "reject"]

# 通用確定性 bounds（capability-specific bounds 在 P3 細化）。
# 為什麼這些值：leverage/size 是最常見的幻覺放大向量；負成本是結構性無效（成本不可為負）。
_LEVERAGE_MAX = 10.0  # 通用上限；超過 → clamp 到此（保守，非 reject 以保留可用 proposal）
_LEVERAGE_MIN = 0.0
_SIZE_FRACTION_MAX = 0.10  # 倉位佔比上限 10%（root principle 16 portfolio-level）
_SIZE_FRACTION_MIN = 0.0


@dataclass
class GuardResult:
    """guard 裁決結果。verdict ∈ {pass, clamp, reject}。"""

    verdict: GuardVerdict
    clamped_output: dict[str, Any] | None = None  # clamp 時為夾值後 output；reject 時 None
    kinds_hit: list[str] = field(default_factory=list)  # 命中的 clause 種類（供 D3 details）


def _clamp_numeric(
    value: Any, lo: float, hi: float
) -> tuple[float | None, bool, bool]:
    """把數值夾進 [lo, hi]。回 (clamped, was_clamped, is_invalid)。

    is_invalid=True：值無法轉 float（結構性無效）→ 呼叫端 reject。
    was_clamped=True：值落在界外被夾。
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None, False, True
    if f != f:  # NaN
        return None, False, True
    if f < lo:
        return lo, True, False
    if f > hi:
        return hi, True, False
    return f, False, False


def guard_output(
    parsed_output: dict[str, Any] | None,
    *,
    guard_ref: str = "",
    context: dict[str, Any] | None = None,
) -> GuardResult:
    """對 parsed_output 跑確定性 guard。proposal 形成「之前」呼叫；無 model 在內。

    P2 通用 clause（capability-specific 在 P3）：
      - range clamp：leverage / size 夾進確定性 bounds；界外 → clamp（夾值後續用）。
      - 結構性無效：負成本（cost/fee/total_cost_bps < 0）→ reject（成本不可為負）。
      - schema：parsed_output 為 None / 非 dict → reject（→ D3 parsed_output=NULL）。
      - no inventing data：欄位引用 available_signal_axes 之外的軸 → reject（P3 細化軸清單）。

    回 GuardResult。verdict=reject ⇒ Orchestrator 不 route 給 applier（logged-and-dropped）。
    """
    ctx = context or {}
    # schema 最小檢：None / 非 dict → reject（結構性無效）。
    if parsed_output is None or not isinstance(parsed_output, dict):
        return GuardResult(verdict="reject", clamped_output=None, kinds_hit=["schema_nonconformant"])

    kinds_hit: list[str] = []
    out = dict(parsed_output)  # 不就地改原物件

    # ── 結構性無效：負成本 → reject（成本不可為負，幻覺向量）──
    for cost_field in ("cost", "cost_bps", "total_cost_bps", "fee", "fee_bps"):
        if cost_field in out:
            try:
                if float(out[cost_field]) < 0:
                    return GuardResult(
                        verdict="reject",
                        clamped_output=None,
                        kinds_hit=["negative_cost"],
                    )
            except (TypeError, ValueError):
                return GuardResult(
                    verdict="reject", clamped_output=None, kinds_hit=["cost_not_numeric"]
                )

    # ── no inventing data：引用 available_signal_axes 之外的軸 → reject ──
    # 為什麼 fail-closed：捏造資料軸 = 幻覺輸入，proposal 不可信（design §E.2 ml_advisory.guard）。
    available_axes = ctx.get("available_signal_axes")
    referenced = out.get("referenced_signal_axes")
    if available_axes is not None and isinstance(referenced, (list, tuple)):
        allowed = set(available_axes)
        invented = [a for a in referenced if a not in allowed]
        if invented:
            return GuardResult(
                verdict="reject",
                clamped_output=None,
                kinds_hit=[f"invented_data_axis:{','.join(map(str, invented))}"],
            )

    # ── range clamp：leverage / size 界外 → clamp（夾值後續用）；NaN/非數值 → reject ──
    if "leverage" in out:
        clamped, was_clamped, invalid = _clamp_numeric(out["leverage"], _LEVERAGE_MIN, _LEVERAGE_MAX)
        if invalid:
            return GuardResult(verdict="reject", clamped_output=None, kinds_hit=["leverage_invalid"])
        if was_clamped:
            out["leverage"] = clamped
            kinds_hit.append("leverage_clamped")

    for size_field in ("size", "size_fraction", "position_fraction"):
        if size_field in out:
            clamped, was_clamped, invalid = _clamp_numeric(
                out[size_field], _SIZE_FRACTION_MIN, _SIZE_FRACTION_MAX
            )
            if invalid:
                return GuardResult(
                    verdict="reject", clamped_output=None, kinds_hit=[f"{size_field}_invalid"]
                )
            if was_clamped:
                out[size_field] = clamped
                kinds_hit.append(f"{size_field}_clamped")

    if kinds_hit:
        return GuardResult(verdict="clamp", clamped_output=out, kinds_hit=kinds_hit)
    return GuardResult(verdict="pass", clamped_output=out, kinds_hit=[])


# ═══════════════════════════════════════════════════════════════════════════════
# P3a — ml_advisory.guard.v1 capability-specific clauses（PA P3 設計 §H；確定性，無 model）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼這些 clause：diagnose/interpret 輸出的「形」風險不同於通用 leverage/size 幻覺——是
#   (1) M3 leak source_class typing（name_pattern_check 不得宣稱 leak-free PIT）；
#   (2) interpret 宣稱 promotion-ready 卻缺 regime_caveat 且 metrics 標 bull-only → reject；
#   (3) signal_axes_used ⊄ available_signal_axes（捏造資料軸）→ reject。
# guard 抓形、math gate 抓實；P3a 無 alpha math gate，故 M3 typing 是 P3a 的主 gate（design §D）。


def _guard_ml_advisory_v1(
    parsed_output: dict[str, Any] | None,
    *,
    context: dict[str, Any] | None = None,
) -> GuardResult:
    """ml_advisory.guard.v1：先跑通用 clause，再跑 P3a capability-specific clause（確定性）。

    為什麼先呼 guard_output：通用 clause（schema-nonconformant / 負成本 / leverage-size / 通用
    axes）仍適用——ml_advisory 輸出若混入這些幻覺向量同樣該擋。capability-specific clause 疊加在
    其上（M3 typing / regime_caveat / per-mode 必填 / signal_axes_used 軸檢）。任一 reject → reject。

    clause（design §E.2(0) lines 868-873 + §F M3 + §E.4 P3b hypothesize）：
      A. per-mode 必填子物件：mode ∈ {diagnose_leak, interpret_result, hypothesize}，且對應子物件
         存在；未知 mode 或缺子物件 → reject（fail-closed）。
      B. M3 source_class typing（diagnose_leak）：evidence[].source_class 必 ∈ 合法集合；任何宣稱
         leak-free PIT（leak_free=true / pit_verified=true）卻 source_class ∉ leak-free 集合
         （只有 shift1_compliance/is_oos_gap 可）→ reject。
      C. regime_caveat（interpret_result）：宣稱 promotion-ready（promotion_ready=true）卻缺非空
         regime_caveat 且 context 標 bull-only → reject（Alpha Evidence Governance）。
      D. signal_axes_used ⊄ available_signal_axes → reject（捏造資料軸；§H clause 1）。
      E. empty-mechanism curve-fit（hypothesize，P3b §E.4(b)）：每個 feature_hypotheses[] 的
         mechanism 必非空字串、falsification_test 必存在 → 否則 reject（無機制 = curve-fit）。
      F. wealth-integrity（hypothesize，P4 §4.2(4)）：falsification_test 必為三欄結構化物件
         （null_hypothesis/test_statistic/reject_condition 非空）+ primary_axis 必 ∈
         signal_axes_used（FDR wealth family 錨點，MIT #4 反 family 鑄幣）→ 否則 reject。
    注意：novelty dedupe（vs dead_failure_modes）「不」在此 guard——它需 DB read（retrieve_lessons
    pg_trgm），而本 guard 的 no-DB 不變量 load-bearing。novelty 在 executor（已做 DB I/O）跑。
    """
    # 動態 import 避免模塊載入期循環（contract registry import layer2_engine；本 guard 不應在
    # import 期被牽連）。常數來自 contract registry（single source，不複製字面集合）。
    from . import l2_prompt_contract_registry as _contracts  # noqa: PLC0415

    ctx = context or {}

    # 先跑通用 clause（schema / 負成本 / leverage-size / 通用 referenced_signal_axes）。
    base = guard_output(parsed_output, guard_ref="ml_advisory.guard.v1", context=ctx)
    if base.verdict == "reject":
        return base  # 通用層已 reject（如 None / 非 dict / 負成本）→ 直接回。

    # base.clamped_output 是通用層處理後的 output（pass/clamp 皆有值）。後續 clause 在其上跑。
    out = base.clamped_output if base.clamped_output is not None else dict(parsed_output or {})
    extra_kinds = list(base.kinds_hit)  # 保留通用層的 clamp 記錄

    # ── clause A：per-mode 必填子物件（fail-closed：未知 mode / 缺子物件 → reject）──
    mode = out.get("mode")
    required = _contracts.ML_ADVISORY_MODE_REQUIRED_FIELDS.get(str(mode)) if mode is not None else None
    if required is None:
        # 未知/缺 mode（含 hypothesize=P3b 不在 P3a 表）→ reject（不放行未知模式輸出）。
        return GuardResult(
            verdict="reject", clamped_output=None,
            kinds_hit=[f"unknown_or_missing_mode:{mode}"],
        )
    missing = [f for f in required if f not in out]
    if missing:
        return GuardResult(
            verdict="reject", clamped_output=None,
            kinds_hit=[f"missing_mode_field:{','.join(missing)}"],
        )

    # ── clause B：M3 source_class typing（diagnose_leak）──
    if mode == "diagnose_leak":
        diag = out.get("leak_drift_diagnosis")
        if not isinstance(diag, dict):
            return GuardResult(
                verdict="reject", clamped_output=None,
                kinds_hit=["leak_drift_diagnosis_not_object"],
            )
        evidence = diag.get("evidence")
        if isinstance(evidence, (list, tuple)):
            for ev in evidence:
                if not isinstance(ev, dict):
                    continue
                sc = ev.get("source_class")
                # B.1：source_class 必填且 ∈ 合法集合（M3 typing 強制；缺/非法 → reject）。
                if sc is None or sc not in _contracts.ML_ADVISORY_LEAK_SOURCE_CLASSES:
                    return GuardResult(
                        verdict="reject", clamped_output=None,
                        kinds_hit=[f"invalid_leak_source_class:{sc}"],
                    )
                # B.2：任何 leak-free PIT 斷言（leak_free/pit_verified）卻 source_class 不在
                # leak-free 集合（只有 shift1_compliance/is_oos_gap 可）→ reject。P3a 只有
                # name_pattern_check producer，故任何 leak-free 斷言在 P3a 必被擋（M3 鐵律）。
                claims_leakfree = bool(ev.get("leak_free")) or bool(ev.get("pit_verified"))
                if claims_leakfree and sc not in _contracts.ML_ADVISORY_LEAKFREE_SOURCE_CLASSES:
                    return GuardResult(
                        verdict="reject", clamped_output=None,
                        kinds_hit=[f"leakfree_claim_unsupported_by_source_class:{sc}"],
                    )

    # ── clause C：regime_caveat when bull-only（interpret_result）──
    if mode == "interpret_result":
        interp = out.get("result_interpretation")
        if not isinstance(interp, dict):
            return GuardResult(
                verdict="reject", clamped_output=None,
                kinds_hit=["result_interpretation_not_object"],
            )
        # bull-only 來自 context（metrics 標籤）或 output 自帶旗標。promotion_ready 斷言來自 output。
        bull_only = bool(ctx.get("bull_only")) or bool(interp.get("bull_only"))
        promotion_ready = bool(interp.get("promotion_ready"))
        regime_caveat = interp.get("regime_caveat")
        has_caveat = isinstance(regime_caveat, str) and regime_caveat.strip() != ""
        # 宣稱 promotion-ready 且 bull-only 卻無 regime_caveat → reject（Alpha Evidence Governance）。
        if promotion_ready and bull_only and not has_caveat:
            return GuardResult(
                verdict="reject", clamped_output=None,
                kinds_hit=["promotion_ready_bull_only_missing_regime_caveat"],
            )

    # ── clause E：empty-mechanism curve-fit（hypothesize，P3b §E.4(b)）──
    # 為什麼 reject 空 mechanism：無經濟機制的假說 = curve-fit（execution-plan §2 Phase 3
    # 「reject empty mechanism」）。每個 feature_hypotheses[] 須有非空 mechanism + falsification_test
    # （可證偽）。math gate 雖是唯一 alpha validator，但「形」上空機制的假說連進 gate 都不該。
    if mode == "hypothesize":
        hyps = out.get("feature_hypotheses")
        if not isinstance(hyps, (list, tuple)):
            return GuardResult(
                verdict="reject", clamped_output=None,
                kinds_hit=["feature_hypotheses_not_list"],
            )
        for h in hyps:
            if not isinstance(h, dict):
                return GuardResult(
                    verdict="reject", clamped_output=None,
                    kinds_hit=["feature_hypothesis_not_object"],
                )
            mech = h.get("mechanism")
            falsif = h.get("falsification_test")
            if not (isinstance(mech, str) and mech.strip()):
                return GuardResult(
                    verdict="reject", clamped_output=None,
                    kinds_hit=[f"empty_mechanism_curve_fit:{h.get('hid')}"],
                )
            # P4 起 falsification_test 必為 v2 結構化物件（三欄在 clause F 驗）；缺 → reject。
            # 自由字串（v1 形）也在 F reject——pre-registration 的 V138 CHECK 要求三欄，
            # 字串形結構上不可能入帳，guard 在「形」層先擋（不浪費後續 stage）。
            if falsif is None:
                return GuardResult(
                    verdict="reject", clamped_output=None,
                    kinds_hit=[f"empty_falsification_test:{h.get('hid')}"],
                )

        # ── clause F：primary_axis ∈ signal_axes_used + falsification 三欄非空（P4 §4.2(4)）──
        # 為什麼 F 是 wealth-integrity clause：primary_axis 決定被扣帳的 FDR family
        # （capability:primary_axis，MIT #4）——宣告不在 signal_axes_used 內的 axis = 開新
        # family 鑄新 W_0 的 wealth-inflation 向量；falsification 三欄是 pre-registration
        # 可證偽紀律的載體（V138 prh_falsification_chk 兜底，guard 前置擋形）。
        top_axes = out.get("signal_axes_used")
        for h in hyps:
            falsif = h.get("falsification_test")
            if not isinstance(falsif, Mapping):
                return GuardResult(
                    verdict="reject", clamped_output=None,
                    kinds_hit=[f"falsification_not_structured:{h.get('hid')}"],
                )
            for fld in ("null_hypothesis", "test_statistic", "reject_condition"):
                v = falsif.get(fld)
                if not (isinstance(v, str) and v.strip()):
                    return GuardResult(
                        verdict="reject", clamped_output=None,
                        kinds_hit=[f"falsification_field_empty:{fld}:{h.get('hid')}"],
                    )
            primary = h.get("primary_axis")
            if not (isinstance(primary, str) and primary.strip()):
                return GuardResult(
                    verdict="reject", clamped_output=None,
                    kinds_hit=[f"primary_axis_missing:{h.get('hid')}"],
                )
            # primary_axis 的合法域 = 該假說自宣告的 signal_axes_used；假說未帶列表時退
            # top-level signal_axes_used（兩者皆無 → 無法證明 membership → reject，fail-closed）。
            h_axes = h.get("signal_axes_used")
            effective_axes = (
                h_axes if isinstance(h_axes, (list, tuple))
                else top_axes if isinstance(top_axes, (list, tuple)) else None
            )
            if effective_axes is None or primary not in effective_axes:
                return GuardResult(
                    verdict="reject", clamped_output=None,
                    kinds_hit=[f"primary_axis_not_in_signal_axes_used:{primary}"],
                )

    # ── clause D：signal_axes_used ⊄ available_signal_axes（捏造資料軸）──
    available_axes = ctx.get("available_signal_axes")
    axes_used = out.get("signal_axes_used")
    if available_axes is not None and isinstance(axes_used, (list, tuple)):
        allowed = set(available_axes)
        invented = [a for a in axes_used if a not in allowed]
        if invented:
            return GuardResult(
                verdict="reject", clamped_output=None,
                kinds_hit=[f"invented_signal_axis:{','.join(map(str, invented))}"],
            )

    # 全 clause 過：沿用通用層的 verdict（pass 或 clamp，保留 clamp 記錄）。
    return GuardResult(
        verdict=base.verdict,
        clamped_output=out,
        kinds_hit=extra_kinds,
    )


# ── callable guard registry（module-level 不可變 dict；frozen at import；stateless）──
# 為什麼 module-level 不可變 dict 而非 mutable singleton：對齊 singleton-registry.md:392
# 「l2_out_of_bound_guard 純確定性函數，無 singleton」。registry 在 import 期一次建成，runtime
# 不 mutate；同 guard_ref 永得同 callable（確定性）。新 capability guard 在此表加一個 entry。
_GUARD_REGISTRY: dict[str, Any] = {
    "ml_advisory.guard.v1": _guard_ml_advisory_v1,
}


def get_guard(guard_ref: str) -> Any:
    """callable guard registry 查詢（P3：回 callable；未註冊 ref → None）。

    為什麼回 callable（非 P2 的 ref echo）：P3 起 capability 有各自 guard clause（ml_advisory.guard.v1
    等）。orchestrator/executor 以 guard_ref 取對應 callable 跑。未註冊 ref 回 None，呼叫端退回通用
    guard_output（fail-safe：未知 guard_ref 不致命，仍跑通用結構網）。
    """
    return _GUARD_REGISTRY.get(guard_ref)


def run_guard(
    parsed_output: dict[str, Any] | None,
    *,
    guard_ref: str = "",
    context: dict[str, Any] | None = None,
) -> GuardResult:
    """依 guard_ref 路由：命中 registry → 跑該 capability guard；否則 → 通用 guard_output。

    為什麼提供 run_guard（而非讓 caller 自己查 + 呼）：把「查 registry → 退通用」的路由收斂在一處，
    orchestrator/executor 只需呼 run_guard(parsed, guard_ref=cap.out_of_bound_guard_ref, context=...)。
    確定性、無 model。
    """
    fn = get_guard(guard_ref)
    if fn is not None:
        return fn(parsed_output, context=context)
    # 未註冊 guard_ref（含 P2 的 ""）→ 退通用 guard_output（fail-safe）。
    return guard_output(parsed_output, guard_ref=guard_ref, context=context)


__all__ = [
    "GuardVerdict",
    "GuardResult",
    "guard_output",
    "get_guard",
    "run_guard",
]
