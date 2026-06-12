"""prompts — L2 記憶蒸餾的兩段 system prompt 常數 + user prompt builder（純函數）。

MODULE_NOTE
模塊用途：提供蒸餾管線的抽取（extraction）與去重裁決（dedup）兩段 system
  prompt 常數，以及對應的 user prompt builder 純函數。builder 零 I/O、零
  network、確定性輸出（同輸入必同輸出），可被單元測試快照。
主要類/函數：Material、EXTRACT_MEMORIES_SYSTEM_PROMPT、
  CONFLICT_DETECTION_SYSTEM_PROMPT、format_extraction_prompt()、
  format_batch_dedup_prompt()、truncate_text()。
依賴：僅 Python 標準庫（json/dataclasses）。
硬邊界：prompt 是 checked-in 確定性模板（PA spec §5），禁止由模型生成或
  運行時改寫；本模組不得 import 任何 app / DB / network 模組。

Attribution（MIT）：
  兩段 prompt 抄改自 TencentCloud/TencentDB-Agent-Memory（MIT License）的
  src/core/prompts/l1-extraction.ts 與 l1-dedup.ts，經中文化 + 交易語義改造
  （persona/episodic/instruction → system_trait/incident/rule）。
  警示：該上游專案服務的外部開源助手恰好也叫「OpenClaw」，與本 repo 的
  OpenClaw 控制面家族同名純屬巧合，無任何代碼或協議關聯，不得互相推斷語義。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# 單條材料文本的截斷上限（與 PA spec §6.2 每欄 4KB cap 對齊；
# builder 端再守一次，防 caller 漏截斷導致 prompt 爆量）。
MATERIAL_TEXT_MAX_CHARS = 4096

# 截斷標記：明示「此處被截斷」，避免 LLM 把斷尾誤讀成完整陳述。
TRUNCATION_MARKER = "…[TRUNCATED]"


# ─────────────────────────────────────────────────────────────────────────────
# 抽取 system prompt（PA spec §5.1 全文；改自 l1-extraction.ts:16-102）
# ─────────────────────────────────────────────────────────────────────────────

EXTRACT_MEMORIES_SYSTEM_PROMPT = """\
你是 OpenClaw 交易系統的「運維情報蒸餾專家」。
你的任務是分析給定的 L2 AI 呼叫記錄與信號失敗報告，從中提取結構化的核心記憶
（僅限 system_trait, incident, rule 三類）。

**輸出語言**：所有自由文本欄位（scene、content）使用繁體中文；技術名詞、代碼
標識、策略名、symbol、JSON 欄位名、枚舉值、ISO 時間戳保持英文。

### 任務一：情境歸納（scene）
為本批材料歸納一個情境名稱（例如「我在覆盤 2026-06-10 的 ml_advisory 診斷呼叫
與 cascade_fade 失敗報告」），30-50 字、單句。

### 任務二：核心記憶提取
【通用提取原則】
1. 寧缺毋濫：過濾一次性操作細節、無結論的中間輸出、純狀態回報；剔除不可靠
   的邊緣信息。每批 0-8 條為宜。
2. 獨立完整：記憶必須「跳出本批材料依然成立」，無上下文也能看懂。主體必須
   明確（哪個策略 / 哪個模組 / 哪類市場狀態）。
3. 歸納合併：強因果關聯的多條材料必須合併為一條完整記憶，不可碎片化。
4. 嚴禁編造：每條記憶必須給出 source_ids（來自材料中的 [id] 標記）；無法
   對應到具體材料的內容不得輸出。

【支持提取的三大類型】（必須嚴格遵守類型規則）
1. 系統特質 (mem_type: "system_trait")
   - 定義：系統、策略、模型、市場結構的穩定屬性與行為模式（如「qwen3.5:9b
     輸出 JSON 偶爾包 markdown fence」「TONUSDT demo 盤口薄、滑點大」）。
   - 句式：「[主體] 在 [條件] 下表現出 [穩定特性]」。
   - priority：80-100（影響風控/資金安全的特質）；50-70（一般行為特性）；
     <50（模糊次要，丟棄）。
2. 事件記憶 (mem_type: "incident")
   - 定義：客觀發生的一次性事件、故障、決定或結果。不含純推測。
   - 句式：「[時間] [主體] 發生 [事件]（起因/經過/結果）」。
   - 時間：盡量從材料 timestamp 推算絕對時間；可確定時在 metadata 填
     activity_start_time / activity_end_time（ISO 8601）。
   - priority：80-100（造成損失/宕機/誤判的事件）；60-70（一般完整事件）；
     <60（瑣碎，丟棄）。
3. 規則記憶 (mem_type: "rule")
   - 定義：應長期遵守的行為規則、檢驗準則、禁令（如「任何短 bias 信號必須
     先做 beta 中性化檢驗」「rolling 窗口含 current bar 必然假 mean-revert」）。
   - 句式：「[條件] 時必須/禁止 [行為]，因為 [理由]」。
   - priority：-1（不可違反的鐵則）；90-100（核心檢驗規則）；70-80（重要
     慣例）；<70（臨時性，丟棄）。

### 不應該提取的內容
- 單次呼叫的中間參數、token 統計、延遲數字
- 與交易/系統運維無關的內容；重複已知的常識
- 純推測（材料中無事實支撐）；AI 自身的客套輸出

### 輸出格式（JSON）
返回且僅返回一個合法 JSON 對象：
{
  "scene": "情境名稱",
  "memories": [
    {
      "content": "完整、獨立的記憶陳述",
      "mem_type": "system_trait|incident|rule",
      "priority": 80,
      "source_ids": ["材料id_1"],
      "event_time_str": "2026-06-10 前後",
      "metadata": {}
    }
  ]
}
無有意義記憶時 memories 為空數組。不要輸出任何 markdown 代碼塊修飾符或解釋文字。
"""


# ─────────────────────────────────────────────────────────────────────────────
# dedup system prompt（PA spec §5.2 全文；改自 l1-dedup.ts:15-69）
# ─────────────────────────────────────────────────────────────────────────────

CONFLICT_DETECTION_SYSTEM_PROMPT = """\
你是 OpenClaw 交易系統的記憶衝突檢測器。批量比較多條【新記憶】與【統一候選
記憶池】中的已有記憶，逐條決定如何處理。

**輸出語言**：merged_content 使用繁體中文（技術名詞保持英文）；JSON 欄位名、
枚舉值、record_id、ISO 時間戳保持英文。

## 核心規則
- 跨類型合併：不同 mem_type（system_trait/incident/rule）的記憶若語義上描述
  同一事實/事件/規則，可以合併；合併後判斷最佳 merged_type。
- 多對多合併：一條新記憶可同時替換候選池中的多條舊記憶（target_ids 數組）。
- 規則升級：同一規則的更精確版本（加了條件、閾值、理由）→ update。
- 事件聚合：同一事故的前因後果 → merge 為一條完整敘述。

## 動作定義
- "store"：新信息，直接新增。
- "skip"：已有記憶更好，新記憶無增量。
- "update"：同一事實，新記憶更具體/更晚/糾錯，以新記憶為主覆蓋。
- "merge"：信息互補不矛盾，合併成一條更完整記憶。

## 輸出格式
嚴格輸出 JSON 數組，每個元素對應一條新記憶的決策，不輸出任何其他內容：
[
  {
    "record_id": "新記憶的 record_id",
    "action": "store|update|skip|merge",
    "target_ids": ["被取代的候選 record_id"],
    "merged_content": "合併/更新後的記憶內容（merge/update 必填）",
    "merged_type": "system_trait|incident|rule（merge/update 必填）",
    "merged_priority": 85
  }
]
target_ids 只能取自該條新記憶的【關聯候選 ID】列表。store/skip 時 target_ids
省略或為空。合併後信息更完整時 merged_priority 可酌情提升。
"""


# ─────────────────────────────────────────────────────────────────────────────
# 材料塊與 builder 純函數
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Material:
    """單條蒸餾材料（pipeline 從 l2_calls / drar 讀出後構造）。

    material_id 規則（PA spec §5.1）：``l2:<l2_reply_id>`` / ``drar:<report_id>``；
    parser 端會以此前綴映射回 source_refs 的 kind。
    """

    material_id: str   # "l2:l2r:abc..." / "drar:123"
    source_kind: str   # "l2_call" / "drar_postmortem"
    ts_iso: str        # ISO 8601（UTC）
    text: str          # 已截斷的材料文本


def truncate_text(text: str, limit: int = MATERIAL_TEXT_MAX_CHARS) -> str:
    """截斷材料文本並附明確標記（冪等：已截斷文本不再重複加標記）。"""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    if text.endswith(TRUNCATION_MARKER):
        return text[:limit]
    return text[: max(0, limit - len(TRUNCATION_MARKER))] + TRUNCATION_MARKER


def format_extraction_prompt(materials: Sequence[Material]) -> str:
    """構造 extraction user prompt（仿 l1-extraction.ts:115-145 結構）。

    頭部聲明 UTC 時區，逐條材料 ``[id] [source_kind] [ISO ts]: <截斷文本>``。
    純函數：不查 DB、不打網路、不讀環境。
    """
    lines: list[str] = [
        "以下為本批待蒸餾材料。所有 timestamp 均為 UTC（ISO 8601）。",
        "每條材料格式：[材料id] [來源類型] [時間戳]: 內容。",
        "提取記憶時 source_ids 必須引用方括號內的材料id 原文。",
        "",
    ]
    for m in materials:
        body = truncate_text(m.text)
        lines.append(f"[{m.material_id}] [{m.source_kind}] [{m.ts_iso}]: {body}")
    return "\n".join(lines)


def format_batch_dedup_prompt(
    new_memories: Sequence[Mapping[str, Any]],
    candidate_pool: Sequence[Mapping[str, Any]],
    related_ids_by_record: Mapping[str, Sequence[str]],
) -> str:
    """構造 batch dedup user prompt（照抄 l1-dedup.ts:94-167 結構）。

    - ``candidate_pool``：統一候選池（全部新記憶召回結果的去重並集），
      以 JSON 形式整體呈現一次（record_id/content/mem_type/priority）。
    - 逐條新記憶附【關聯候選 ID】= 該條自身召回的 top-5 record_id 列表，
      LLM 的 target_ids 只允許取自此列表（parser 端二次強制，越界降 store）。
    - 池空短路（省一次 LLM call）由 pipeline 負責；本函數對空池仍可構造
      （防御性），但正常路徑不會被呼叫。
    純函數：確定性 JSON 序列化（sort_keys + ensure_ascii=False）。
    """
    pool_view = [
        {
            "record_id": str(c.get("record_id", "")),
            "content": truncate_text(str(c.get("content", "")), 1024),
            "mem_type": str(c.get("mem_type", "")),
            "priority": c.get("priority", 50),
        }
        for c in candidate_pool
    ]
    lines: list[str] = [
        "## 統一候選記憶池（已有記憶）",
        json.dumps(pool_view, ensure_ascii=False, sort_keys=True, indent=1),
        "",
        "## 新記憶（逐條裁決）",
    ]
    for nm in new_memories:
        rid = str(nm.get("record_id", ""))
        related = [str(x) for x in related_ids_by_record.get(rid, [])]
        lines.append(
            json.dumps(
                {
                    "record_id": rid,
                    "content": truncate_text(str(nm.get("content", "")), 1024),
                    "mem_type": str(nm.get("mem_type", "")),
                    "priority": nm.get("priority", 50),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        lines.append(f"【關聯候選 ID】{json.dumps(related, ensure_ascii=False)}")
    lines.append("")
    lines.append("對每條新記憶輸出一個裁決元素，嚴格按 system prompt 的 JSON 數組格式。")
    return "\n".join(lines)
