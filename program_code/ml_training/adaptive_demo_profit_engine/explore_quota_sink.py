"""
MODULE_NOTE (中):
  用途：Track1 demo explore-gate 的 Python 側 **additive sink**。把 allocator
  對每個 arm 的「探索額度（explore_budget - n_trials）」與「是否仍在探索期」
  落到 settings/edge_estimates.json 的對應 cell，讓 Rust demo cost_gate
  （cost_gate_moderate_with_slippage）在「樣本不足才探索」語意下把 reject 翻成
  探索放行（受 Guardian/Kelly/P1 cap/准入全鏈 + explore_budget 上限約束）。

  主要函數：
    - build_explore_overlay(allocator, current_regime, candidate_cells)：純函數。
      對每個 'strategy::symbol' cell，查 allocator 在 (current_regime, strategy) arm
      的真實 explore_budget_remaining → 推導 {explore_eligible, explore_remaining}。
    - merge_into_edge_estimates(overlay, edge_estimates_path, dry_run, apply)：IO 層。
      讀現有 edge_estimates.json → **只 additive 注入 2 欄**（不覆蓋 JS writer 的
      shrunk_bps/n/win_rate/_meta）→ 原子寫回（temp + os.replace）。

  依賴：
    - program_code.ml_training.regime_bandit_allocator.RegimeBanditAllocator
      （explore_budget_remaining / make_arm_id，allocator 是探索信號的唯一真實來源）。
    - settings/edge_estimates.json（demo+live 共用檔，但 explore 欄位只被 demo gate 讀）。

  硬邊界 / 誠實鐵則（為什麼這樣設計）：
    1. **explore_eligible 必須真實從 allocator n_trials 衍生**。
       explore_remaining = explore_budget_remaining(arm) = max(0, budget - n_trials)；
       explore_eligible = (remaining > 0)。**嚴禁寫死全 true**——那會把 99.97%-reject
       直接翻成全放行、繞過「樣本不足才探索」語意、曝險失控（design §8.3）。
    2. **additive merge，不踩既有 writer**。james_stein_estimator._write_json_snapshot
       是 edge_estimates.json 的另一 writer。本 sink 讀現有檔後只新增 explore_eligible /
       explore_remaining 兩欄，原樣保留所有既有欄位與 _meta，避免 lost-update 互踩
       （design §8.2，E2 必驗）。
    3. **dry_run 默認 true，真寫需 apply=True**。鏡像 ADPE runner 哲學：默認只產
       overlay + log，operator 確認後才落檔。dry_run=True 絕不寫檔。
    4. **fail-closed / additive：缺 cell / 缺欄位 = 不探索**。overlay 只標註現有
       cell（gate 已關心的 'strategy::symbol'）；不憑空建 cell。Rust 端 JSON 缺欄
       → unwrap_or(false/0) → 回退現行 block（absence = no-explore，design §3.1）。
    5. **demo only**。sink 只寫 edge_estimates.json；explore 欄位只被 demo gate 讀，
       live gate（gates.rs cost_gate_live_with_slippage）不引用新欄位 → 天然隔離。
       caller（runner）已硬鎖 engine_mode='demo'。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from program_code.ml_training.regime_bandit_allocator import (
    RegimeBanditAllocator,
    make_arm_id,
)

logger = logging.getLogger(__name__)

# edge_estimates.json 的 cell key 分隔符（'strategy::symbol'，與 james_stein_estimator
# _write_json_snapshot 同源）。`_meta` 是唯一無 '::' 的頂層 key，必須跳過。
_CELL_SEP = "::"
_META_KEY = "_meta"

# additive 注入的兩個 explore 欄位名（與 Rust CellEstimate / parse_object 解析的鍵一致）。
_FIELD_ELIGIBLE = "explore_eligible"
_FIELD_REMAINING = "explore_remaining"


def _split_cell_key(cell_key: str) -> Optional[tuple[str, str]]:
    """把 'strategy::symbol' 拆成 (strategy, symbol)；非 cell key（如 _meta）回 None。

    為什麼用 partition 而非 split：strategy / symbol 本身不含 '::'，但 partition
    對首個 '::' 切分最穩健（即使下游詞彙演進也不會誤切）。空段一律視為非法 cell。
    """
    if cell_key == _META_KEY or _CELL_SEP not in cell_key:
        return None
    strategy, _sep, symbol = cell_key.partition(_CELL_SEP)
    strategy = strategy.strip()
    symbol = symbol.strip()
    if not strategy or not symbol:
        return None
    return strategy, symbol


def build_explore_overlay(
    allocator: RegimeBanditAllocator,
    current_regime: str,
    candidate_cells: list[str],
) -> dict[str, dict]:
    """純函數：對每個 'strategy::symbol' cell 推導 explore overlay。

    參數：
      allocator：已 ingest 過 realized reward 的 RegimeBanditAllocator（探索信號唯一
        真實來源；本函數不修改它，只唯讀查 explore_budget_remaining）。
      current_regime：當前 regime（design §3.3 regime 維度在 Python 端 collapse；
        gate 無 regime 上下文，故 regime 判斷留在已有 regime 上下文的 Python 端）。
      candidate_cells：要標註的 cell key 列表（'strategy::symbol'），通常 = 現有
        edge_estimates.json 的 cell（gate 已關心的格子）。

    回：{cell_key: {explore_eligible: bool, explore_remaining: int}}。

    誠實鐵則（design §8.3）：
      - explore_remaining 真實 = allocator.explore_budget_remaining(arm)（n_trials 衍生）；
      - explore_eligible = (explore_remaining > 0)，即「此 arm 在當前 regime 仍在探索期
        （樣本不足以可靠判負）」。allocator 已 ingest 足量樣本（remaining=0）→ eligible=False
        → gate 回退現行 block（誠實死，非永久釘死：regime 轉折後 allocator 的
        forgetting_gamma 衰減舊統計、n_trials 縮回探索期，remaining 重新 > 0）。
      - **絕不寫死 explore_eligible=True**。eligible 完全由 allocator 真實狀態決定。

    symbol fan-out（design §3.3）：allocator arm = (regime, strategy) 無 symbol 維，
      故同 strategy 的所有 symbol 共享 explore 狀態（per-symbol explore 是未來 allocator
      arm-space 擴展，非 Track1 範圍）。本函數對每個 symbol cell 查同一 (regime, strategy)
      arm。
    """
    overlay: dict[str, dict] = {}
    for cell_key in candidate_cells:
        parsed = _split_cell_key(cell_key)
        if parsed is None:
            # 非 cell key（_meta / 形狀異常）→ 不標註，跳過（fail-closed：不憑空建）。
            continue
        strategy, _symbol = parsed
        arm_id = make_arm_id(current_regime, strategy)
        # 唯一真實信號：allocator 的 explore_budget_remaining（= max(0, budget - n_trials)）。
        remaining = int(allocator.explore_budget_remaining(arm_id))
        eligible = remaining > 0
        overlay[cell_key] = {
            _FIELD_ELIGIBLE: eligible,
            _FIELD_REMAINING: remaining,
        }
    return overlay


def merge_into_edge_estimates(
    overlay: dict[str, dict],
    edge_estimates_path: str,
    *,
    dry_run: bool = True,
    apply: bool = False,
) -> dict:
    """IO 層：把 overlay additive 注入 edge_estimates.json（不覆蓋既有 writer 欄位）。

    參數：
      overlay：build_explore_overlay 的輸出 {cell_key: {explore_eligible, explore_remaining}}。
      edge_estimates_path：settings/edge_estimates.json 絕對路徑（呼叫端提供，不硬編）。
      dry_run：True（預設）只產 merge plan，**不寫檔**。
      apply：True 才真寫（與 ADPE runner --apply 哲學一致；dry_run=True 時 apply 被忽略）。

    回：審計 dict {dry_run, wrote, n_overlay, n_merged, n_missing, path}。
      - n_merged：overlay 中有對應現有 cell 而被注入的數量。
      - n_missing：overlay 中無對應現有 cell（gate 看不到的格子）→ 不憑空建（additive 守恆）。

    additive 守恆（design §8.2，E2 命門）：
      讀現有 snapshot → 只對「已存在的 cell」就地塞 2 個 explore 欄位 → 其餘欄位、
      _meta、未在 overlay 的 cell 全部原樣保留 → 原子 temp + os.replace 寫回。
      不新增 cell、不刪欄位、不改 _meta，故與 james_stein_estimator writer 不互踩
      （唯一例外：兩者皆寫同檔，時序上後寫者勝；建議 sink 在 JS writer 之後跑）。

    fail-closed：檔不存在 / 解析失敗 → 回 wrote=False + reason，不部分寫、不憑空建檔
      （Rust 端缺 explore 欄位自動回退現行 block，absence = no-explore）。
    """
    result: dict = {
        "dry_run": dry_run,
        "wrote": False,
        "n_overlay": len(overlay),
        "n_merged": 0,
        "n_missing": 0,
        "path": edge_estimates_path,
    }

    # 讀現有 snapshot（additive 的前提：不讀就寫 = 覆蓋 JS writer，違鐵則 2）。
    try:
        with open(edge_estimates_path, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
    except FileNotFoundError:
        # 缺檔 → 不憑空建（Rust 缺檔自有 fail-closed 行為；sink 不負責建 baseline）。
        result["reason"] = "edge_estimates_not_found"
        logger.warning("explore sink: edge_estimates.json 不存在，不寫: %s", edge_estimates_path)
        return result
    except (json.JSONDecodeError, OSError) as e:
        result["reason"] = f"edge_estimates_parse_error: {e}"
        logger.warning("explore sink: edge_estimates.json 解析失敗，不寫: %s", e)
        return result

    if not isinstance(snapshot, dict):
        result["reason"] = "edge_estimates_not_object"
        logger.warning("explore sink: edge_estimates.json 頂層非 object，不寫")
        return result

    # additive 注入：只標註「已存在的 cell」，其餘原樣保留。
    n_merged = 0
    n_missing = 0
    for cell_key, fields in overlay.items():
        existing = snapshot.get(cell_key)
        if isinstance(existing, dict):
            # 就地塞 2 欄（既有欄位、_meta、未提及的 cell 全不動）。
            existing[_FIELD_ELIGIBLE] = bool(fields.get(_FIELD_ELIGIBLE, False))
            existing[_FIELD_REMAINING] = int(fields.get(_FIELD_REMAINING, 0))
            n_merged += 1
        else:
            # overlay 提到但現有 snapshot 無此 cell → 不憑空建（additive 守恆）。
            n_missing += 1
    result["n_merged"] = n_merged
    result["n_missing"] = n_missing

    # dry_run 或非 apply → 只回 plan，不寫檔。
    if dry_run or not apply:
        logger.info(
            "explore sink dry-run: n_overlay=%d n_merged=%d n_missing=%d (未寫 %s)",
            len(overlay), n_merged, n_missing, edge_estimates_path,
        )
        return result

    # 真寫：原子 temp + os.replace（鏡像 james_stein_estimator._write_json_snapshot）。
    os.makedirs(os.path.dirname(os.path.abspath(edge_estimates_path)), exist_ok=True)
    tmp = edge_estimates_path + ".explore.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    os.replace(tmp, edge_estimates_path)  # atomic rename / 原子重命名
    result["wrote"] = True
    logger.info(
        "explore sink wrote: n_merged=%d n_missing=%d → %s",
        n_merged, n_missing, edge_estimates_path,
    )
    return result
