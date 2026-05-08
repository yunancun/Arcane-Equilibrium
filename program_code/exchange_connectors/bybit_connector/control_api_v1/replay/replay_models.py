"""REF-20 Paper Replay Lab — Pydantic request models (extracted for LOC cap).
REF-20 Paper Replay Lab — Pydantic 請求模型（為 LOC 上限抽出）。

MODULE_NOTE (EN):
    Sprint A R1-T3 (2026-05-04) extraction. The 3 request models below
    used to live inline in ``app/replay_routes.py`` (lines 154-243 of
    that file pre-extraction). They are pulled out here so adding the
    ``/api/v1/replay/health`` route to ``replay_routes.py`` does not push
    that file past the ``CLAUDE.md §九 1500 LOC`` hard cap.

    Behaviour is byte-identical to the inline form: same class names,
    same field shapes, same validators, same docstrings. ``replay_routes``
    re-imports them as module-level aliases so prior callers and tests
    keep working unchanged.

MODULE_NOTE (中):
    Sprint A R1-T3（2026-05-04）抽出。下方 3 個請求模型原本內嵌在
    ``app/replay_routes.py``（抽出前該檔 154-243 行）。為了在
    ``replay_routes.py`` 新增 ``/api/v1/replay/health`` 路由時不破
    ``CLAUDE.md §九 1500 LOC`` 硬上限而抽出。

    行為與內嵌完全相同：同 class 名、同 field shape、同 validator、
    同 docstring。``replay_routes`` 把它們以模組級別名重新 import 進來，
    既有 caller 與測試完全不變。

SPEC: REF-20 V3 §4.1 schema (manifest experiment_id) +
      Sprint A Gap Closure Plan §6.R1 (LOC governance).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models / 請求響應模型
# ═══════════════════════════════════════════════════════════════════════════════


class ReplayRunRequest(BaseModel):
    """POST /run body — start a replay run.
    POST /run body — 啟動一次 replay run。

    Wave 4 wiring: validates shape + auth, then spawns replay_runner
    subprocess via OPENCLAW_REPLAY_RUNNER_BIN. Concurrency cap enforced
    via PG advisory lock (primary) or in-memory dict (fallback).
    Wave 4 接線：驗 shape + auth，然後透過 OPENCLAW_REPLAY_RUNNER_BIN
    spawn replay_runner 子程序。並發上限由 PG advisory lock（主路徑）
    或 in-memory dict（fallback）強制。
    """

    experiment_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Pre-registered manifest experiment_id (V3 §4.1 schema)",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=128,
        description=(
            "Optional idempotency key per V3 §4.1 lineage; if provided "
            "and matches an existing run for this actor, return cached."
        ),
    )

    @field_validator("experiment_id")
    def _validate_experiment_id(cls, v: str) -> str:
        # Alphanumeric + hyphen/underscore only (path-injection guard).
        # 只允許字母數字+連字號/底線（防 path injection）。
        v = v.strip()
        if not v:
            raise ValueError("experiment_id cannot be empty")
        for ch in v:
            if not (ch.isalnum() or ch in "-_"):
                raise ValueError(
                    "experiment_id may only contain alphanumeric, hyphen, or underscore"
                )
        return v


class ReplayCancelRequest(BaseModel):
    """POST /cancel body — cancel currently running replay.
    POST /cancel body — 取消當前運行中的 replay。
    """

    experiment_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description=(
            "If set, only cancel if the active run matches this id; "
            "guards against stale GUI state cancelling a fresher run."
        ),
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Operator-supplied cancellation reason (audit row).",
    )


class ReplayManifestVerifyRequest(BaseModel):
    """POST /manifest/verify body — verify HMAC signature of a manifest.
    POST /manifest/verify body — 驗證 manifest 的 HMAC 簽名。
    """

    canonical_bytes_b64: str = Field(
        ...,
        min_length=1,
        description="Base64-encoded canonical manifest bytes.",
    )
    declared_hash_hex: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Declared sha256 hex digest of the body.",
    )
    signature_hex: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Declared HMAC-SHA256 signature (hex).",
    )
    fingerprint: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="16-char key fingerprint (per helper script algorithm).",
    )


__all__ = [
    "ReplayRunRequest",
    "ReplayCancelRequest",
    "ReplayManifestVerifyRequest",
]
