#!/usr/bin/env python3
"""S2.4(WP4)receipt 發射的持久化邊界葉模組(2000 行治理拆分;P2-I 收口)。

自 ``agent_governance_s2_4_install`` 下沉的**寫入面**——三個 wave 發射器共用:

- evidence 防呆(形狀 + 中央 secret-like 深掃;寧可拒發射,不可把密鑰寫進 repo);
- **不靜默覆蓋**:任一目標檔已存在即 typed 拒絕且零寫入,覆蓋必須是顯式動作
  (``allow_overwrite=True`` / CLI ``--allow-overwrite``)。已發射的 receipt 會被上游
  derivation/lineage digest 綁定,靜默覆蓋等同無聲改寫治理歷史;
- CLI ``--out`` 受限於 repo 的 receipts 目錄(symlink 解析後),不得把治理 receipt 寫到
  任意路徑。API 層刻意仍接受任意 ``out_dir``(disposable 測試用 tmp_path)。

零 effect、零 authority:本模組只做「寫或不寫」的邊界判定,不導出任何 status。
``agent_governance_s2_4_install`` 逐名 re-export,既有匯入面/monkeypatch 縫不變。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPTS_ROOT = REPO_ROOT / "docs" / "execution_plan" / "ai_ml_landing" / "receipts"


def resolve_cli_out_dir(out_dir: Path, *, receipts_root: Path = RECEIPTS_ROOT) -> Path:
    """把 CLI 的 --out 解析並約束在 repo receipts 目錄內;越界即 typed 拒絕。"""

    resolved = Path(out_dir).resolve()
    root = Path(receipts_root).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(
            f"--out must stay inside the repository receipts directory {root}: {resolved}"
        )
    return resolved


def persist_emit_artifacts(
    out_dir: Path,
    artifacts: tuple[tuple[str, Any], ...],
    *,
    allow_overwrite: bool,
) -> list[str] | None:
    """先檢查再寫;已存在且未顯式允許覆蓋 → 回碰撞清單且**零寫入**(全有全無)。"""

    existing = sorted(name for name, _ in artifacts if (out_dir / name).exists())
    if existing and not allow_overwrite:
        return existing
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, artifact in artifacts:
        (out_dir / name).write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return None


def emit_collision_refusal(status: str, existing: list[str]) -> dict[str, Any]:
    """發射碰撞的 typed 拒絕(共用;stage 固定為 output_collision)。"""

    return {
        "status": status,
        "stage": "output_collision",
        "reasons": [
            "receipt output already exists; pass allow_overwrite=True (CLI: "
            f"--allow-overwrite) to replace it deliberately: {name}"
            for name in existing
        ],
    }


def validate_emit_evidence(
    test_evidence: Any, review_provenance: Any, *, secret_scanner: Any
) -> None:
    """三個發射器共用的 evidence 防呆(E3 P2-4 含 secret 深掃)。

    persisted evidence 會逐字進入 Git-committed receipt 檔;除形狀檢查外,以中央
    secret-like 內容掃描拒絕任何疑似機密的 evidence(``secret_scanner`` 由 caller 注入
    中央 validator 的實作,避免本葉重造判準)。
    """

    if not isinstance(test_evidence, dict) or not test_evidence:
        raise ValueError("test_evidence must be a non-empty object")
    if not isinstance(review_provenance, list) or not review_provenance or not all(
        isinstance(item, dict) and item for item in review_provenance
    ):
        raise ValueError("review_provenance must be a non-empty list of objects")
    if secret_scanner(test_evidence) or secret_scanner(review_provenance):
        raise ValueError(
            "emit evidence contains secret-like content; refusing to persist"
        )


__all__ = [
    "RECEIPTS_ROOT",
    "emit_collision_refusal",
    "persist_emit_artifacts",
    "resolve_cli_out_dir",
    "validate_emit_evidence",
]
