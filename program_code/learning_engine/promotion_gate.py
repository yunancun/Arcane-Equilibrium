"""Composite DSR/PBO promotion gate for strategy promotion.

策略晉升用 DSR/PBO 複合門控。

This module wires the already-implemented DSR(K) and PBO/CSCV math gates into a
single fail-closed result that production promotion callers can consume.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional, Sequence

import numpy as np

from .dsr_gate import DsrGate, DsrResult
from .pbo_gate import PboGate, PboResult


PromotionVerdict = Literal["promote", "borderline", "block", "defer_data"]


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@dataclass(frozen=True)
class SelectionBiasPromotionResult:
    """Composite DSR/PBO result.

    DSR/PBO 複合結果。
    """

    verdict: PromotionVerdict
    passes: bool
    reasons: tuple[str, ...]
    dsr: DsrResult
    dsr_verdict: str
    pbo: Optional[PboResult]
    pbo_verdict: str
    cpcv_protocol: str

    def to_dict(self) -> dict:
        """Return JSON-compatible diagnostics for audit/status surfaces."""
        return {
            "verdict": self.verdict,
            "passes": self.passes,
            "reasons": list(self.reasons),
            "dsr": _json_safe(asdict(self.dsr)),
            "dsr_verdict": self.dsr_verdict,
            "pbo": _json_safe(asdict(self.pbo)) if self.pbo is not None else None,
            "pbo_verdict": self.pbo_verdict,
            "cpcv_protocol": self.cpcv_protocol,
        }


class SelectionBiasPromotionGate:
    """Enforce DSR(K) + PBO/CSCV before strategy promotion.

    在策略晉升前強制 DSR(K) + PBO/CSCV。
    """

    def __init__(
        self,
        *,
        dsr_gate: Optional[DsrGate] = None,
        pbo_gate: Optional[PboGate] = None,
    ) -> None:
        self._dsr_gate = dsr_gate or DsrGate()
        self._pbo_gate = pbo_gate or PboGate()

    def evaluate(
        self,
        *,
        observed_sharpe: float,
        n_trials: int,
        n_observations: int,
        candidate_oos_returns: Optional[Sequence[Sequence[float]]] = None,
        trial_sharpes: Optional[Sequence[float]] = None,
    ) -> SelectionBiasPromotionResult:
        """Evaluate DSR and PBO/CSCV evidence.

        評估 DSR 與 PBO/CSCV 證據。
        """
        reasons: list[str] = []

        dsr = self._dsr_gate.compute_dsr(
            observed_sharpe=observed_sharpe,
            n_trials=n_trials,
            n_observations=n_observations,
            trial_sharpes=trial_sharpes,
        )
        dsr_verdict = self._dsr_gate.gate(dsr)
        if dsr_verdict != "promote":
            reasons.append(f"dsr_{dsr_verdict}")

        pbo: Optional[PboResult] = None
        pbo_verdict = "missing_cpcv_returns"
        if candidate_oos_returns is None or len(candidate_oos_returns) < 2:
            reasons.append("pbo_missing_cpcv_returns")
        else:
            pbo_arrays = [
                np.asarray(candidate_returns, dtype=np.float64)
                for candidate_returns in candidate_oos_returns
            ]
            pbo = self._pbo_gate.compute_pbo(pbo_arrays)
            if pbo.insufficient_power:
                pbo_verdict = "defer_data"
                reasons.append("pbo_insufficient_power")
            else:
                pbo_verdict = self._pbo_gate.gate(pbo)
                if pbo_verdict != "promote":
                    reasons.append("pbo_above_threshold")

        verdict: PromotionVerdict
        if dsr_verdict == "block" or pbo_verdict == "block":
            verdict = "block"
        elif pbo_verdict in ("missing_cpcv_returns", "defer_data"):
            verdict = "defer_data"
        elif dsr_verdict == "borderline":
            verdict = "borderline"
        else:
            verdict = "promote"

        return SelectionBiasPromotionResult(
            verdict=verdict,
            passes=verdict == "promote",
            reasons=tuple(reasons),
            dsr=dsr,
            dsr_verdict=dsr_verdict,
            pbo=pbo,
            pbo_verdict=pbo_verdict,
            cpcv_protocol="cscv",
        )
