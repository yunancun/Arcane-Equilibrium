"""AEG-S2 breadth ladder — artifact-level survivorship healthcheck（MIT b.6）。

MODULE_NOTE:
  模塊用途：``check_aeg_breadth_universe_pit()``——機械化 FND-2 acceptance gate，抓
    silent regression 回 current-survivor。**artifact-level**（讀 breadth_ladder_summary
    .json + FND-2 universe_summary.json），**非 DB freshness**（(b) 0 DB 表）。
  主要函數：``check_aeg_breadth_universe_pit(breadth_summary_path, fnd2_summary_path)``。
  斷言（PA §6 / MIT b.6）：
    - 消費的 universe（任一 tier，至少 full_survivorship）在窗含 delisted 時必有
      delisted-proof → ``delisted_proof_total >= 1``（FND-2 真跑 255，遠超）。
    - 若 ``delisted_proof_total == 0`` 但 FND-2 summary
      ``survivor_rejection_status != PROVEN_NONE_IN_WINDOW`` → **FAIL**（universe 被
      silently truncate 成 current-survivor）。
    - ``survivorship_inherited_from_fnd2 == true``（(b) 沒自寫 mask）。
  硬邊界：
    - **read-only**，0 寫、0 DB。CLAUDE「passive wait 須 healthcheck」滿足（artifact
      讀取而非 DB freshness——(b) 無 DB 表，故 freshness 定義在 artifact 層）。
    - 放置決策（E1，待 PM/E2 確認）：因本檢查 0-DB / artifact-level，與
      ``db/passive_wait_healthcheck/`` 的 DB-cursor `check_*(cur)` 契約不同型，故置於
      breadth ladder package 內作獨立可測函數，cron wrapper 可呼用（mirror FND-2 的
      artifact-only 紀律——FND-2 亦未塞進 DB-cursor runner）。
  依賴：標準庫（json / pathlib）。import-time 零 DB / 零外部依賴。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def _read_json(path: Optional[Path]) -> Optional[dict]:
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def check_aeg_breadth_universe_pit(
    breadth_summary_path,
    fnd2_summary_path,
) -> tuple:
    """artifact-level survivorship PIT 健康檢查。回 ``(status, message)``。

    status ∈ {'PASS','FAIL','WARN'}（mirror passive_wait check_* 三態語義）：
      - WARN：artifact 缺（summary 找不到）→ 不打 FAIL（artifact 可能尚未生成）。
      - FAIL：窗內有 delisted 證據但 breadth universe truncate 成 current-survivor
        （delisted_proof_total==0 但 FND-2 survivor_rejection_status != PROVEN_NONE）；
        或 survivorship_inherited_from_fnd2 != true（(b) 疑自寫 mask）。
      - PASS：delisted-proof 充分 + survivorship 繼承自證。
    """
    breadth = _read_json(breadth_summary_path)
    fnd2 = _read_json(fnd2_summary_path)

    if breadth is None:
        return ("WARN", f"breadth_ladder_summary.json 缺：{breadth_summary_path}")
    if fnd2 is None:
        return ("WARN", f"FND-2 universe_summary.json 缺：{fnd2_summary_path}")

    # 1) survivorship 繼承自證（(b) 沒自寫 mask）。
    inherited = breadth.get("survivorship_inherited_from_fnd2")
    if inherited is not True:
        return (
            "FAIL",
            "breadth summary survivorship_inherited_from_fnd2 != true "
            f"(got {inherited!r}) — (b) 疑自寫 mask 而非繼承 FND-2",
        )

    # 2) delisted-proof 充分性（抓 current-survivor truncation regression）。
    delisted_total = int(breadth.get("delisted_proof_total", 0) or 0)
    fnd2_status = fnd2.get("survivor_rejection_status")
    if delisted_total == 0:
        if fnd2_status != "PROVEN_NONE_IN_WINDOW":
            return (
                "FAIL",
                "breadth delisted_proof_total==0 但 FND-2 survivor_rejection_status="
                f"{fnd2_status!r}（非 PROVEN_NONE_IN_WINDOW）→ universe 疑被 silently "
                "truncate 成 current-survivor（FND-2 acceptance gate 機械化失守）",
            )
        # FND-2 已證窗內無 delisted（PROVEN_NONE）→ delisted_proof_total==0 合法。
        return (
            "PASS",
            "delisted_proof_total==0 與 FND-2 PROVEN_NONE_IN_WINDOW 一致（窗內無 delisted）",
        )

    # 3) 正常路徑：delisted-proof >= 1。
    return (
        "PASS",
        f"breadth delisted_proof_total={delisted_total} (>=1) + survivorship 繼承自證 "
        f"(FND-2 status={fnd2_status})",
    )


__all__ = ["check_aeg_breadth_universe_pit"]
