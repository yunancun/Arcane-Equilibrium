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
  - get_guard(guard_ref):registry 查詢（P2 通用 guard；capability-specific clause 在 P3）。

依賴：無 model、無 DB；純函數 + 確定性 bounds。

硬邊界：
  - 確定性：guard 內**無 model 呼叫**（CC/E2 grep target）；同輸入永得同 verdict。
  - 在 record_l2_call 寫 parsed_output「之前」跑；reject ⇒ proposal「永不」route 給 applier
    （logged-and-dropped）。
  - clamp ⇒ clamped_output 才是後續使用的值（非原始幻覺值）。
  - 純 guard：無 order surface、無 lease、無 promote。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

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


def get_guard(guard_ref: str) -> str:
    """registry 查詢佔位（P2 僅通用 guard_output；capability-specific guard 在 P3 註冊）。

    回傳 guard_ref 本身作為 echo（P2 無多 guard 變體）；P3 改為回 callable registry。
    """
    return guard_ref


__all__ = [
    "GuardVerdict",
    "GuardResult",
    "guard_output",
    "get_guard",
]
