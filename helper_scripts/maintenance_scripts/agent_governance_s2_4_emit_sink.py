#!/usr/bin/env python3
"""S2.4(WP4)receipt 發射的持久化邊界葉模組(2000 行治理拆分;P2-I 收口)。

自 ``agent_governance_s2_4_install`` 下沉的**寫入面**——三個 wave 發射器共用:

- evidence 防呆(形狀 + 中央 secret-like 深掃;寧可拒發射,不可把密鑰寫進 repo);
- **不靜默覆蓋**:任一目標檔已存在即 typed 拒絕且零寫入,覆蓋必須是顯式動作
  (``allow_overwrite=True`` / CLI ``--allow-overwrite``)。已發射的 receipt 會被上游
  derivation/lineage digest 綁定,靜默覆蓋等同無聲改寫治理歷史;
- **整組原子發佈**(P2-1):一次發射的 3~5 個 artifact 是一個不可分割的集合。序列化全部
  先做完、再落 staging 檔、最後才逐一以「獨佔建立」(``os.link``,EEXIST 即碰撞)或
  ``os.replace`` 推上正位;任一步失敗即回滾本次已發佈者(新建的刪除、被覆蓋的還原
  原位元組),絕不留下半套。並發面以目錄內的獨佔 lock 檔(``O_CREAT|O_EXCL``)串行化——
  舊碼的「先檢查再寫」讓兩個並行發射器可以雙雙通過檢查再交錯寫入,把兩條 lineage 混在
  同一個目錄裡;半套殘留則會讓下一次重試把自己的殘骸看成碰撞而拒絕復原;
- CLI ``--out`` 受限於 repo 的 receipts 目錄(symlink 解析後),不得把治理 receipt 寫到
  任意路徑。API 層刻意仍接受任意 ``out_dir``(disposable 測試用 tmp_path)。

零 effect、零 authority:本模組只做「寫或不寫」的邊界判定,不導出任何 status。
``agent_governance_s2_4_install`` 逐名 re-export,既有匯入面/monkeypatch 縫不變。
"""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPTS_ROOT = REPO_ROOT / "docs" / "execution_plan" / "ai_ml_landing" / "receipts"
# 發佈邊界:同一輸出目錄同時只允許一個發射器(獨佔建立;結束即移除)。
PUBLICATION_LOCK_NAME = ".s2-4-receipt-publication.lock"
_STAGING_PREFIX = ".s2-4-receipt-staging-"
# 硬連結不被支援時的退路(仍在發佈 lock 內,互斥不變)。
_LINK_UNSUPPORTED_ERRNOS = frozenset({
    errno.EPERM,
    errno.ENOSYS,
    errno.EOPNOTSUPP,
    errno.EXDEV,
})


def resolve_cli_out_dir(out_dir: Path, *, receipts_root: Path = RECEIPTS_ROOT) -> Path:
    """把 CLI 的 --out 解析並約束在 repo receipts 目錄內;越界即 typed 拒絕。"""

    resolved = Path(out_dir).resolve()
    root = Path(receipts_root).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(
            f"--out must stay inside the repository receipts directory {root}: {resolved}"
        )
    return resolved


def _serialize_artifacts(
    artifacts: tuple[tuple[str, Any], ...]
) -> list[tuple[str, bytes]]:
    """P2-1:任何 I/O 之前先把整組序列化完——序列化失敗不可能留下半套檔案。"""

    return [
        (
            name,
            (
                json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
        )
        for name, artifact in artifacts
    ]


def _write_staging_file(path: Path, payload: bytes) -> None:
    """落 staging 位元組並 fsync(推上正位之前,內容必須已在裝置上)。

    staging 檔名是本次發射私有的(pid+序號+目標名)且整段持有發佈 lock,故以 O_TRUNC
    覆寫殘骸即可——若改用 O_EXCL,前一次崩潰留下的同名殘骸會被誤報成「輸出碰撞」。
    """

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rollback_published(
    out_dir: Path, published: list[tuple[str, bytes | None]]
) -> None:
    """回滾本次已推上正位者:新建的刪除、被覆蓋的還原原位元組(盡力而為)。"""

    for name, previous in reversed(published):
        target = out_dir / name
        try:
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(previous)
        except OSError:  # noqa: PERF203 - 回滾失敗不得掩蓋原始失敗原因
            continue


def persist_emit_artifacts(
    out_dir: Path,
    artifacts: tuple[tuple[str, Any], ...],
    *,
    allow_overwrite: bool,
) -> dict[str, Any] | None:
    """整組原子發佈;成功回 None,任何拒絕回 typed ``{stage, reasons}`` 且零殘留。

    順序即語義:序列化(零 I/O 失敗面)→ 獨佔 lock(並發串行化)→ 碰撞檢查 →
    staging 落檔 + fsync → 逐一推上正位(不覆蓋模式以 ``os.link`` 獨佔建立,EEXIST 即
    碰撞;覆蓋模式先留存原位元組再 ``os.replace``)→ 任一步失敗即回滾整組。
    """

    payloads = _serialize_artifacts(artifacts)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return {"stage": "output_directory", "reasons": [f"output directory is unusable: {error}"]}

    lock_path = out_dir / PUBLICATION_LOCK_NAME
    try:
        lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return {
            "stage": "publication_lock",
            "reasons": [
                "another receipt emitter holds the publication lock for this output "
                f"directory (remove it only after confirming no emitter is running): {lock_path}"
            ],
        }
    except OSError as error:
        return {
            "stage": "publication_lock",
            "reasons": [f"publication lock is unusable: {error}"],
        }
    os.write(lock_fd, f"{os.getpid()}\n".encode("ascii"))
    os.close(lock_fd)

    staged: list[tuple[str, Path]] = []
    published: list[tuple[str, bytes | None]] = []
    try:
        existing = sorted(name for name, _ in payloads if (out_dir / name).exists())
        if existing and not allow_overwrite:
            return _collision_refusal(existing)
        for index, (name, payload) in enumerate(payloads):
            staging_path = out_dir / f"{_STAGING_PREFIX}{os.getpid()}-{index}-{name}"
            _write_staging_file(staging_path, payload)
            staged.append((name, staging_path))
        for name, staging_path in staged:
            target = out_dir / name
            previous: bytes | None = None
            if allow_overwrite and target.exists():
                previous = target.read_bytes()
                os.replace(staging_path, target)
            else:
                # 獨佔建立:EEXIST 是核心層級的碰撞判定(先檢查再寫的競態在此關閉)。
                try:
                    os.link(staging_path, target)
                except OSError as error:
                    if error.errno in _LINK_UNSUPPORTED_ERRNOS:
                        # 檔案系統不支援硬連結:退回 rename(互斥仍由發佈 lock 保證)。
                        os.replace(staging_path, target)
                    else:
                        raise
                else:
                    staging_path.unlink()
            published.append((name, previous))
    except FileExistsError:
        _rollback_published(out_dir, published)
        return _collision_refusal(sorted(name for name, _ in payloads))
    except OSError as error:
        _rollback_published(out_dir, published)
        return {
            "stage": "publication",
            "reasons": [
                "receipt set could not be published atomically; the partial set was "
                f"rolled back: {error}"
            ],
        }
    finally:
        for _name, staging_path in staged:
            try:
                staging_path.unlink(missing_ok=True)
            except OSError:  # noqa: PERF203 - staging 清理失敗不得掩蓋結果
                pass
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
    return None


def _collision_refusal(existing: list[str]) -> dict[str, Any]:
    return {
        "stage": "output_collision",
        "reasons": [
            "receipt output already exists; pass allow_overwrite=True (CLI: "
            f"--allow-overwrite) to replace it deliberately: {name}"
            for name in existing
        ],
    }


def emit_collision_refusal(status: str, refusal: dict[str, Any]) -> dict[str, Any]:
    """發射拒絕的 typed 包裝(共用;stage/reasons 由 :func:`persist_emit_artifacts` 給)。"""

    return {"status": status, **refusal}


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
    "PUBLICATION_LOCK_NAME",
    "RECEIPTS_ROOT",
    "emit_collision_refusal",
    "persist_emit_artifacts",
    "resolve_cli_out_dir",
    "validate_emit_evidence",
]
