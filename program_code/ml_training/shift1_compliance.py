"""shift1_compliance — M3 leak-free PIT producer（薄 adapter，重用 feature_engineering_validator）。

MODULE_NOTE
模塊用途：
  L2 Phase 3b M3 leak-typing producer（PA P3b 設計 §C + MIT §1.1）。emit source_class=
  "shift1_compliance" 的 typed evidence row，使 hypothesize 的「leak-free」斷言合法（vs
  name_pattern_check 這個 necessary-not-sufficient screen，guard B.2 會 reject 它的 leak-free
  斷言）。

  ★ 重用而非新算法：helper_scripts/m4/feature_engineering_validator.py 已實作 shift1 的實質
    （is_leaky_sql / is_leakfree_sql / is_leaky_pandas / validate_shift1_pattern）。本模塊只
    呼叫這些函式並組 typed row。

主要類/函數：
  - Shift1ComplianceResult：dataclass（source_class / leak_free / per_feature / reasons /
    evidence_ref）。
  - check_shift1_compliance(...)：兩層（static + empirical）per feature 檢查。

依賴：
  - helper_scripts.m4.feature_engineering_validator（is_leaky_sql / is_leakfree_sql /
    is_leaky_pandas / validate_shift1_pattern）——無新 leak 算法。

硬邊界：
  - leak_free=True「只」當每個 feature 都 pass 且無 defer（fail-closed：任一 DEFER →
    leak_free=False，不是 leak-free 斷言）。
  - leak_suspected → fail；insufficient_sample → DEFER（never auto-pass on thin data）。
  - 純 compute：0 DB 寫、0 order path。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

# 重用既有 leak 驗證（無新算法）。
from helper_scripts.m4.feature_engineering_validator import (
    is_leakfree_sql,
    is_leaky_pandas,
    is_leaky_sql,
    validate_shift1_pattern,
)

# M3 typed source_class（與 l2_prompt_contract_registry.ML_ADVISORY_LEAKFREE_SOURCE_CLASSES 對齊）。
SOURCE_CLASS = "shift1_compliance"

# per-feature verdict 字面值（fail-closed 三態）。
_PASS = "pass"
_FAIL = "fail"
_DEFER = "defer"


@dataclass
class Shift1ComplianceResult:
    """shift1_compliance 裁決結果（M3 typed evidence row）。

    leak_free=True 只當每 feature pass 且無 defer（fail-closed）。per_feature 是 audit 載體
    （static + empirical 細節）。
    """

    source_class: str                     # 恆 "shift1_compliance"
    leak_free: bool
    per_feature: list[dict[str, Any]]     # [{feature, verdict, static{...}, empirical{...}}]
    reasons: list[str] = field(default_factory=list)
    evidence_ref: str = ""                # training_run_id + feature_definition_hash（provenance）

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_class": self.source_class,
            "leak_free": self.leak_free,
            "per_feature": list(self.per_feature),
            "reasons": list(self.reasons),
            "evidence_ref": self.evidence_ref,
        }


def check_shift1_compliance(
    feature_series: Mapping[str, Sequence[float]],
    forward_return_bps: Sequence[float],
    *,
    window: int,
    compute_exprs: Optional[Mapping[str, str]] = None,
    diff_threshold: float = 0.1,
    evidence_ref: str = "",
) -> Shift1ComplianceResult:
    """per feature 跑兩層 shift(1) leak 檢查（static + empirical），emit typed evidence row。

    參數：
      - feature_series：{feature_name: realized values, time-ordered}（pipeline 已產的實值序列）。
      - forward_return_bps：對齊的 forward return（label proxy）。
      - window：rolling window（與 validate_shift1_pattern 一致）。
      - compute_exprs：可選 {feature_name: SQL/pandas source}；提供時跑 static 檢查。
      - diff_threshold：leak-vs-clean correlation diff 門檻（預設 0.1，validate_shift1_pattern）。
      - evidence_ref：provenance（training_run_id + feature_definition_hash）。

    回 Shift1ComplianceResult。leak_free=True 只當每 feature pass 且無 defer（fail-closed）。
    """
    per_feature: list[dict[str, Any]] = []
    reasons: list[str] = []
    any_fail = False
    any_defer = False

    if not feature_series:
        # 無 feature → 無法證 leak-free（fail-closed：空集不 auto-pass）。
        return Shift1ComplianceResult(
            source_class=SOURCE_CLASS, leak_free=False, per_feature=[],
            reasons=["no_features_provided"], evidence_ref=evidence_ref,
        )

    for feature, values in feature_series.items():
        static = _run_static(feature, compute_exprs)
        empirical = validate_shift1_pattern(
            list(values), list(forward_return_bps), window, diff_threshold=diff_threshold
        )

        verdict = _PASS
        # static leak（SQL CURRENT ROW / pandas rolling 無 shift）→ fail（結構性 leak）。
        if static.get("leaky_sql") or static.get("leaky_pandas"):
            verdict = _FAIL
        # empirical leak（leak-vs-clean corr diff > threshold）→ fail（行為性 leak）。
        elif empirical.get("leak_suspected"):
            verdict = _FAIL
        # 樣本不足 → DEFER（never auto-pass on thin data；MIT §1.1.1）。
        elif empirical.get("insufficient_sample"):
            verdict = _DEFER

        if verdict == _FAIL:
            any_fail = True
            reasons.append(f"{feature}:leak_suspected")
        elif verdict == _DEFER:
            any_defer = True
            reasons.append(f"{feature}:insufficient_sample")

        per_feature.append({
            "feature": feature,
            "verdict": verdict,
            "static": static,
            "empirical": {
                "leak_corr": empirical.get("leak_corr"),
                "clean_corr": empirical.get("clean_corr"),
                "diff": empirical.get("diff"),
                "leak_suspected": empirical.get("leak_suspected"),
                "insufficient_sample": empirical.get("insufficient_sample"),
            },
        })

    # fail-closed：leak_free 只當「無 fail 且無 defer」（任一 DEFER → 不是 leak-free 斷言）。
    leak_free = not any_fail and not any_defer
    return Shift1ComplianceResult(
        source_class=SOURCE_CLASS,
        leak_free=leak_free,
        per_feature=per_feature,
        reasons=_dedupe(reasons),
        evidence_ref=evidence_ref,
    )


def _run_static(
    feature: str, compute_exprs: Optional[Mapping[str, str]]
) -> dict[str, Any]:
    """static 結構檢查（compute_expr 可用時跑 is_leaky_*/is_leakfree_sql）。

    為什麼 static 是可選層：compute_expr（SQL/pandas source）不一定隨 realized series 提供；
    有則跑結構網（AND CURRENT ROW = leak；AND 1 PRECEDING = leak-free proof），無則只靠
    empirical 層。
    """
    if not compute_exprs or feature not in compute_exprs:
        return {"available": False, "leaky_sql": False, "leakfree_sql": False, "leaky_pandas": False}
    expr = str(compute_exprs[feature])
    return {
        "available": True,
        "leaky_sql": is_leaky_sql(expr),
        "leakfree_sql": is_leakfree_sql(expr),
        "leaky_pandas": is_leaky_pandas(expr),
    }


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


__all__ = [
    "SOURCE_CLASS",
    "Shift1ComplianceResult",
    "check_shift1_compliance",
]
