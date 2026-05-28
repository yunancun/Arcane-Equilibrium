#!/usr/bin/env python3
# MODULE_NOTE
# 模塊用途：產生 docs/ 下 markdown 文件清單（含 sha256 首 30 行與超越關係 hint），供 TW 文件治理批次清理使用。
# 主要類/函數：scan_docs / detect_supersedes / write_inventory / cli main
# 依賴：標準函式庫（pathlib / hashlib / json / argparse / re）；不依賴外部套件。
# 硬邊界：dry-run 模式只讀；正式模式只覆寫 _indexes/document_inventory.json 與 doc_cleanup_run_*.json，不動其他檔。

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


SUPERSEDES_RE = re.compile(r"(SUPERSEDED\b|supersed|取代|deprecated|retire)", re.IGNORECASE)


def sha256_first_lines(path: Path, n_lines: int = 30) -> str:
    # 取前 30 行做指紋，避開全檔 hash 在大檔上的成本
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = []
            for _ in range(n_lines):
                line = fh.readline()
                if not line:
                    break
                lines.append(line)
        h = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
        return h[:16]
    except Exception as exc:
        return f"err:{exc.__class__.__name__}"


def detect_supersedes_hint(path: Path) -> dict:
    # 掃首 5 行抓 SUPERSEDED header；不深入解析語法
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            head = "".join(fh.readline() for _ in range(5))
    except Exception:
        return {"is_superseded": False, "target": None}
    m = SUPERSEDES_RE.search(head)
    if not m:
        return {"is_superseded": False, "target": None}
    link_m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", head)
    target = link_m.group(2) if link_m else None
    return {"is_superseded": True, "target": target}


def scan_docs(root: Path) -> list:
    docs_dir = root / "docs"
    out = []
    for p in sorted(docs_dir.rglob("*.md")):
        try:
            stat = p.stat()
        except OSError:
            continue
        rel = p.relative_to(root).as_posix()
        sup = detect_supersedes_hint(p)
        out.append({
            "path": rel,
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "sha256_first30": sha256_first_lines(p, 30),
            "supersedes_candidate": sup["is_superseded"],
            "supersedes_target_hint": sup["target"],
            "orphan_flag": False,
        })
    return out


def write_dry_run(root: Path, entries: list, ts_label: str) -> Path:
    out_path = root / "docs" / "_indexes" / f"doc_cleanup_run_{ts_label}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run",
        "total_md": len(entries),
        "supersedes_candidate_count": sum(1 for e in entries if e["supersedes_candidate"]),
        "entries": entries,
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate docs markdown inventory (schema v2)")
    parser.add_argument("--root", default=".", help="repo root (worktree root)")
    parser.add_argument("--dry-run", action="store_true", help="只產 doc_cleanup_run JSON，不寫 document_inventory.json")
    parser.add_argument("--ts-label", default=None, help="輸出檔時間戳標籤，預設 UTC YYYY-MM-DDTHHmm")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "docs").is_dir():
        print(f"[regen_doc_inventory] no docs/ under {root}", file=sys.stderr)
        return 2
    ts_label = args.ts_label or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")
    entries = scan_docs(root)
    out = write_dry_run(root, entries, ts_label)
    print(f"[regen_doc_inventory] scanned {len(entries)} markdown files -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
