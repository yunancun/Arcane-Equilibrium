"""
MODULE_NOTE
模塊用途：Hidden-OOS **sealer**（補 experiment_registry/source_contract 只有 schema+
validator、無 sealer 寫 sealed-state 的缺口）。為候選 family 封存一個**保留未開封**的
OOS 窗，產出同時通過 source_contract 兩個 gate（migration-free manifest gate +
durable gate）的 sealed hidden_oos_state，並給出 source_row 須一致的 commitment 欄位。
主要函數：build_hidden_oos_state、hidden_oos_source_row_fields、compute_split_hash。
依賴：candidate_evidence_source_contract（schema 常數）；僅標準庫；不讀 DB。
硬邊界：state 硬寫 sealed / open_count=0 / opened_for_iteration=consumed=invalidated=False
（封存即未開封，open-once 由消費端維護）；durable body 與 manifest 內 hidden_oos_state
**必為同一物件**（source_contract 比對兩者 canonical sha256 須相等）；OOS 窗須與
calibration/candidate 窗**不重疊**（caller 責任，sealer 只封裝其承諾）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

try:  # 套件式 import
    from program_code.ml_training.candidate_evidence_source_contract import (
        HIDDEN_OOS_STATE_SCHEMA_VERSION,
    )
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from ml_training.candidate_evidence_source_contract import (  # type: ignore
        HIDDEN_OOS_STATE_SCHEMA_VERSION,
    )


HIDDEN_OOS_SEALED_STATE = "sealed"


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_split_hash(
    *,
    family_id: str,
    calibration_window: tuple[str, str],
    candidate_window: tuple[str, str],
    oos_window: tuple[str, str],
    embargo_seconds: int,
    total_candidates_k: int,
) -> str:
    """對 (family + 三窗 + embargo + K) 做 canonical sha256（hex64）。封存承諾的指紋。"""
    return _canonical_sha256(
        {
            "family_id": str(family_id),
            "calibration_window": list(calibration_window),
            "candidate_window": list(candidate_window),
            "oos_window": list(oos_window),
            "embargo_seconds": int(embargo_seconds),
            "total_candidates_k": int(total_candidates_k),
        }
    )


def build_hidden_oos_state(
    *,
    family_id: str,
    calibration_window: tuple[str, str],
    candidate_window: tuple[str, str],
    oos_window: tuple[str, str],
    embargo_seconds: int,
    total_candidates_k: int,
    residual_report_hash: str = "",
) -> dict[str, Any]:
    """封存一個 sealed hidden_oos_state。

    ``oos_window`` 是保留、residual 計算**未觸碰**的窗（window_start/end 對外即此窗）；
    calibration=train 擬合窗、candidate=eval 評估窗。state 硬寫 sealed/未開封。
    """
    split_hash = compute_split_hash(
        family_id=family_id,
        calibration_window=calibration_window,
        candidate_window=candidate_window,
        oos_window=oos_window,
        embargo_seconds=embargo_seconds,
        total_candidates_k=total_candidates_k,
    )
    return {
        "schema_version": HIDDEN_OOS_STATE_SCHEMA_VERSION,
        "state": HIDDEN_OOS_SEALED_STATE,
        "open_count": 0,
        "opened_for_iteration": False,
        "consumed": False,
        "invalidated": False,
        "family_id": str(family_id),
        "split_hash": split_hash,
        "calibration_window": {"start": calibration_window[0], "end": calibration_window[1]},
        "candidate_window": {"start": candidate_window[0], "end": candidate_window[1]},
        "oos_window": {"start": oos_window[0], "end": oos_window[1]},
        "window_start": oos_window[0],
        "window_end": oos_window[1],
        "embargo_seconds": int(embargo_seconds),
        "total_candidates_k": int(total_candidates_k),
        "residual_hash": str(residual_report_hash),
    }


def hidden_oos_source_row_fields(
    state: Mapping[str, Any],
    *,
    base_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """回傳 source_row 須帶、與 sealed state 一致的全部欄位。

    durable body 與 manifest 內 hidden_oos_state 用**同一 state**（source_contract 比對
    兩者 canonical sha256 須相等）。base_manifest 若給，hidden_oos_state 併入其上。
    """
    manifest = dict(base_manifest or {})
    manifest["hidden_oos_state"] = state
    return {
        "replay_registry_manifest_jsonb": manifest,
        "durable_hidden_oos_state": HIDDEN_OOS_SEALED_STATE,
        "durable_hidden_oos_state_jsonb": state,
        "replay_registry_oos_label_window_start": state["window_start"],
        "replay_registry_oos_label_window_end": state["window_end"],
        "replay_registry_oos_embargo_seconds": int(state["embargo_seconds"]),
        "replay_registry_total_candidates_k": int(state["total_candidates_k"]),
    }


__all__ = [
    "HIDDEN_OOS_SEALED_STATE",
    "compute_split_hash",
    "build_hidden_oos_state",
    "hidden_oos_source_row_fields",
]
