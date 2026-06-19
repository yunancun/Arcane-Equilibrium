"""Minimal Hypothesis / SignalSpec adapter for AEG research packets."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROGRAM_CODE = _REPO_ROOT / "program_code"
if str(_PROGRAM_CODE) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE))

from ml_training.candidate_signal_spec import (  # noqa: E402
    SIGNAL_SPEC_SCHEMA_VERSION,
    compute_signal_spec_hash,
    validate_signal_spec,
)


def build_signal_spec(
    *,
    candidate_id: str,
    family_id: str,
    hypothesis: str,
    horizon: dict[str, Any],
    inputs: list[str],
    universe_ref: dict[str, Any],
    regime_ref: dict[str, Any],
    feature_schema: dict[str, Any],
    cost_model_ref: dict[str, Any],
    residualization: dict[str, Any],
    failure_taxonomy: list[str],
    hidden_oos_policy: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """建立 canonical SignalSpec，並嵌入穩定 spec_hash。"""
    spec: dict[str, Any] = {
        "schema_version": SIGNAL_SPEC_SCHEMA_VERSION,
        "candidate_id": str(candidate_id),
        "family_id": str(family_id),
        "hypothesis": str(hypothesis),
        "horizon": dict(horizon),
        "inputs": list(inputs),
        "pit_contract": {
            "point_in_time": True,
            "future_data_allowed": False,
        },
        "universe_ref": dict(universe_ref),
        "regime_ref": dict(regime_ref),
        "feature_schema": dict(feature_schema),
        "cost_model_ref": dict(cost_model_ref),
        "residualization": dict(residualization),
        "failure_taxonomy": list(failure_taxonomy),
        "hidden_oos_policy": dict(hidden_oos_policy),
    }
    if extra:
        spec.update(dict(extra))
    spec["spec_hash"] = compute_signal_spec_hash(spec)
    return spec


def validate_signal_manifest(signal_spec: Any) -> dict[str, Any]:
    """回傳 dict，讓 research artifact 可 JSON serialize。"""
    validation = validate_signal_spec(signal_spec)
    return {
        "ok": validation.ok,
        "verdict": validation.verdict,
        "reason": validation.reason,
        "reasons": list(validation.reasons),
        "spec_hash": validation.spec_hash,
    }


__all__ = ["build_signal_spec", "validate_signal_manifest"]
