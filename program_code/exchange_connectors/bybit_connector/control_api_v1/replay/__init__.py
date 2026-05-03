"""REF-20 Paper Replay Lab — Python control-API surface.
REF-20 Paper Replay Lab — Python 控制 API 平面。

MODULE_NOTE (EN):
    Wave 2 P2a-S2 scaffold export. This package currently re-exports only the
    `manifest_signer` module — a Python mirror of the Rust `ManifestSigner`
    (rust/openclaw_engine/src/replay/manifest_signer.rs) that produces
    byte-equal HMAC-SHA256 tags for the same (canonical_bytes, key) pair.
    Future Wave 2/3 sub-tasks land:
      - manifest canonicalizer (P2a-S4)
      - quota / TTL / per-actor enforcer (P2a-S5)
      - 8 routes auth scaffolding (P2a-S3) under control_api_v1/app/
      - safe_query mirror (P2a-S12)

MODULE_NOTE (中):
    Wave 2 P2a-S2 scaffold 匯出。本 package 目前僅 re-export `manifest_signer`
    模組 — Rust `ManifestSigner` 的 Python 鏡像，對相同 (canonical_bytes, key)
    產出 byte-equal HMAC-SHA256 tag。後續 Wave 2/3 子任務會落地 canonicalizer
    / quota / 8 routes auth / safe_query mirror。

SPEC: REF-20 V3 §3 G2 + §5
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P2a-S2
"""

from .manifest_signer import (  # noqa: F401
    InMemoryKeyArchive,
    KeyArchive,
    KeyStatus,
    ManifestSigner,
    SignatureFailMode,
    compute_body_hash,
    compute_key_fingerprint,
)

__all__ = [
    "InMemoryKeyArchive",
    "KeyArchive",
    "KeyStatus",
    "ManifestSigner",
    "SignatureFailMode",
    "compute_body_hash",
    "compute_key_fingerprint",
]
