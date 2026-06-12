"""parsing — LLM JSON 輸出解析（兩段差異化 fail 策略）。

MODULE_NOTE
模塊用途：解析蒸餾管線兩段 LLM 輸出（extraction / dedup），含 markdown
  fence 剝除、結構校驗、欄位白名單與 per-row 容錯。
主要類/函數：ExtractionResult、MemoryCandidate、DedupDecision、
  strip_markdown_fence()、parse_extraction_response()、parse_dedup_response()。
依賴：僅 Python 標準庫（json/dataclasses/re）。
硬邊界（PA spec §6.3，E2 審查重點 2，兩段策略不可互換）：
  - extraction parse fail ⇒ 整批 skip（ok=False，caller 不推進游標）。
    為什麼不能 fail-open：extraction 失敗時沒有「解析出的記憶」可存，任何
    兜底產物都等於偽造 AI 產物（CLAUDE 硬邊界「不得 fake AI 呼叫產物」）。
  - dedup parse fail ⇒ fail-open-to-store（逐條降 store：INSERT 新記憶、
    不動舊記憶）。為什麼 fail-open：寧可暫時重複，不可丟失或誤刪——重複
    會被未來輪次 dedup 收斂；丟失/誤刪不可逆（DELETE 已被 V139 REVOKE）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

# 三類交易語義（與 V139 chk_agent_memory_mem_type 對齊）。
VALID_MEM_TYPES: frozenset[str] = frozenset({"system_trait", "incident", "rule"})

# dedup 四動作（與 PA spec §5.2 對齊）。
VALID_DEDUP_ACTIONS: frozenset[str] = frozenset({"store", "skip", "update", "merge"})

# 分類型 priority 丟棄線（R4 幻覺緩解第二層：prompt 指示 + parser 強制雙層）。
# rule 的 -1（鐵則）為唯一例外，clamp 後等於 -1 仍保留。
_PRIORITY_FLOOR: dict[str, int] = {"system_trait": 50, "incident": 60, "rule": 70}

# content 長度上限（防 LLM 失控長輸出灌庫；4KB 與材料截斷 cap 同級）。
_CONTENT_MAX_CHARS = 4096

# markdown fence 剝除：```json ... ``` / ``` ... ```（qwen 系常見包裹，R2）。
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)


def strip_markdown_fence(text: str) -> str:
    """剝除整體包裹的 markdown code fence；無 fence 時原樣返回（冪等）。"""
    if not text:
        return ""
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text.strip()


def _clamp_priority(value: Any) -> int | None:
    """priority 轉 int 並 clamp 到 [-1, 100]；不可轉換回 None（該條丟棄）。

    為什麼 clamp 而非整條拒絕：測試計劃明定「priority 越界 clamp 到 [-1,100]」
    （PA spec §13.1）；非數值才視為結構壞損丟棄。bool 是 int 子類，顯式排除。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None
    return max(-1, min(100, iv))


@dataclass(frozen=True)
class MemoryCandidate:
    """extraction 段解析出的單條合格記憶候選（尚未分配 record_id）。"""

    content: str
    mem_type: str
    priority: int
    source_ids: tuple[str, ...]
    event_time_str: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionResult:
    """extraction 段解析結果。

    ok=False ⇒ 整批 skip + 游標不推進（caller 責任）；ok=True 且 memories
    為空 ⇒ 當批無有意義記憶，屬合法成功（游標照常推進）。
    """

    ok: bool
    scene: str = ""
    memories: tuple[MemoryCandidate, ...] = ()
    error: str = ""
    dropped_count: int = 0  # 逐條校驗被丟棄的條數（觀測用）


def parse_extraction_response(
    text: str,
    allowed_source_ids: Sequence[str],
) -> ExtractionResult:
    """解析 extraction LLM 輸出。

    整體結構壞損（非 JSON / 非 dict / memories 非 list）⇒ ok=False（整批 skip）。
    單條記憶壞損（缺欄 / mem_type 非法 / source_ids 缺失或越界 / priority
    非數值 / 低於分類型丟棄線）⇒ 丟棄該條（寧缺毋濫），不影響整批。

    source_ids 強制（R4 幻覺緩解）：每個 id 必須出現在 allowed_source_ids
    （本批材料 id 全集）中；任一越界即整條丟棄——無法溯源的記憶不入庫。
    """
    allowed = {str(s) for s in allowed_source_ids}
    cleaned = strip_markdown_fence(text or "")
    try:
        obj = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        return ExtractionResult(ok=False, error=f"extraction_json_invalid: {exc}")

    if not isinstance(obj, dict):
        return ExtractionResult(ok=False, error="extraction_not_object")
    raw_memories = obj.get("memories")
    if not isinstance(raw_memories, list):
        return ExtractionResult(ok=False, error="extraction_memories_not_list")

    scene = obj.get("scene")
    scene_str = scene.strip() if isinstance(scene, str) else ""

    kept: list[MemoryCandidate] = []
    dropped = 0
    for item in raw_memories:
        cand = _validate_memory_item(item, allowed)
        if cand is None:
            dropped += 1
            continue
        kept.append(cand)
    return ExtractionResult(
        ok=True, scene=scene_str, memories=tuple(kept), dropped_count=dropped
    )


def _validate_memory_item(
    item: Any, allowed_source_ids: set[str]
) -> MemoryCandidate | None:
    """單條記憶白名單校驗；任何不合格回 None（丟棄）。"""
    if not isinstance(item, Mapping):
        return None
    content = item.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    mem_type = item.get("mem_type")
    if mem_type not in VALID_MEM_TYPES:
        return None
    priority = _clamp_priority(item.get("priority"))
    if priority is None:
        return None
    # 分類型丟棄線；rule 的 -1 鐵則例外。
    if not (mem_type == "rule" and priority == -1):
        if priority < _PRIORITY_FLOOR[mem_type]:
            return None
    raw_sids = item.get("source_ids")
    if not isinstance(raw_sids, list) or not raw_sids:
        return None
    sids = [str(s) for s in raw_sids]
    if any(s not in allowed_source_ids for s in sids):
        return None
    ets = item.get("event_time_str")
    ets_str = ets.strip() if isinstance(ets, str) else ""
    meta = item.get("metadata")
    meta_dict = dict(meta) if isinstance(meta, Mapping) else {}
    return MemoryCandidate(
        content=content.strip()[:_CONTENT_MAX_CHARS],
        mem_type=str(mem_type),
        priority=priority,
        source_ids=tuple(sids),
        event_time_str=ets_str,
        metadata=meta_dict,
    )


@dataclass(frozen=True)
class DedupDecision:
    """dedup 段對單條新記憶的裁決（已通過白名單校驗或被降為 store）。"""

    record_id: str
    action: str                      # store|skip|update|merge
    target_ids: tuple[str, ...] = ()
    merged_content: str = ""
    merged_type: str = ""
    merged_priority: int | None = None
    fail_open: bool = False          # True = 該條因解析/校驗失敗被降 store


def _store_fallback(record_id: str, reason: str) -> DedupDecision:
    """fail-open-to-store 統一出口（記 log 供觀測，不 raise）。"""
    logger.warning("dedup fail-open-to-store record=%s reason=%s", record_id, reason)
    return DedupDecision(record_id=record_id, action="store", fail_open=True)


def parse_dedup_response(
    text: str,
    new_record_ids: Sequence[str],
    allowed_targets_by_record: Mapping[str, Sequence[str]],
) -> list[DedupDecision]:
    """解析 dedup LLM 輸出，保證對每條新記憶恰好回一個裁決。

    fail-open-to-store（E2 審查重點 2，僅此段允許）：
      - 整體非 JSON / 非數組 ⇒ 全部新記憶降 store。
      - 單行缺 record_id / record_id 未知或重複 / action 非法 /
        target_ids 越界（不在該條關聯候選列表）/ merge|update 缺
        merged_content 或 merged_type 非法 ⇒ 該條降 store。
      - LLM 漏答的新記憶 ⇒ 降 store。
    任何路徑都不返回「丟棄」：新記憶必入庫（重複可被未來輪次收斂）。
    """
    ordered_ids = [str(r) for r in new_record_ids]
    id_set = set(ordered_ids)
    cleaned = strip_markdown_fence(text or "")
    rows: list[Any]
    try:
        parsed = json.loads(cleaned)
        rows = parsed if isinstance(parsed, list) else []
        batch_ok = isinstance(parsed, list)
    except (json.JSONDecodeError, ValueError):
        rows = []
        batch_ok = False

    decisions: dict[str, DedupDecision] = {}
    if batch_ok:
        for row in rows:
            if not isinstance(row, Mapping):
                continue  # 無 record_id 可歸屬；對應記憶最終走漏答降 store
            rid = str(row.get("record_id", ""))
            if rid not in id_set or rid in decisions:
                continue  # 未知/重複 record_id：丟棄該行，記憶走漏答降 store
            decisions[rid] = _validate_dedup_row(
                rid, row, [str(t) for t in allowed_targets_by_record.get(rid, [])]
            )
    else:
        logger.warning("dedup batch parse fail → 全部 fail-open-to-store")

    # 保證輸出按 new_record_ids 原序、一一對應；漏答降 store。
    out: list[DedupDecision] = []
    for rid in ordered_ids:
        out.append(decisions.get(rid) or _store_fallback(rid, "missing_row"))
    return out


def _validate_dedup_row(
    record_id: str, row: Mapping[str, Any], allowed_targets: list[str]
) -> DedupDecision:
    """單行裁決白名單校驗；任何不合格降 store（絕不 raise、絕不丟棄）。"""
    action = row.get("action")
    if action not in VALID_DEDUP_ACTIONS:
        return _store_fallback(record_id, f"invalid_action:{action!r}")

    raw_targets = row.get("target_ids") or []
    if not isinstance(raw_targets, list):
        return _store_fallback(record_id, "target_ids_not_list")
    targets = [str(t) for t in raw_targets]

    if action in ("store", "skip"):
        # store/skip 不得攜帶 target（防誤 supersede）；有殘留即忽略 target。
        return DedupDecision(record_id=record_id, action=str(action))

    # update / merge：target 必須非空且全部在關聯候選列表內（越界=幻覺，降 store）。
    if not targets:
        return _store_fallback(record_id, "update_merge_without_targets")
    allowed_set = set(allowed_targets)
    if any(t not in allowed_set for t in targets):
        return _store_fallback(record_id, "target_ids_out_of_candidates")

    merged_content = row.get("merged_content")
    if not isinstance(merged_content, str) or not merged_content.strip():
        return _store_fallback(record_id, "merged_content_missing")
    merged_type = row.get("merged_type")
    if merged_type not in VALID_MEM_TYPES:
        return _store_fallback(record_id, f"merged_type_invalid:{merged_type!r}")
    merged_priority = _clamp_priority(row.get("merged_priority"))

    return DedupDecision(
        record_id=record_id,
        action=str(action),
        target_ids=tuple(targets),
        merged_content=merged_content.strip()[:_CONTENT_MAX_CHARS],
        merged_type=str(merged_type),
        merged_priority=merged_priority,
    )
