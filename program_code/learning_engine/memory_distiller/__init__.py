"""memory_distiller — L2 結構化記憶層蒸餾管線 package。

MODULE_NOTE
模塊用途：把每日 agent.l2_calls + gate 報告（V131 drar → signal_postmortem
  taxonomy）經本地 LLM 蒸餾成三類結構化記憶（system_trait/incident/rule），
  存入 agent.agent_memory（V139），並提供三級降級召回與 B3 dormant 接縫。
主要子模組：prompts / parsing / store / recall / embedding / pipeline /
  backfill_embeddings。
依賴：標準庫 + learning_engine.signal_postmortem；DB 連線與 LLM client
  全部 caller 注入（cron CLI 經 get_local_llm_client()），import 時零網路
  零 DB 連線。
硬邊界：純學習記憶層（root principle 7），對 l2_calls/drar 唯讀，寫入唯一
  目標 = agent.agent_memory；全 flag 家族 OPENCLAW_L2_MEMORY_* 默認 OFF。

Attribution（MIT）：設計與兩段 prompt 抄改自 TencentCloud/TencentDB-Agent-Memory
  （MIT License）。警示：該上游專案服務的外部開源助手恰好也叫「OpenClaw」，
  與本 repo 的 OpenClaw 控制面家族同名純屬巧合，無任何代碼或協議關聯。
"""

from .embedding import OllamaEmbeddingClient, detect_meta_drift
from .parsing import (
    DedupDecision,
    ExtractionResult,
    MemoryCandidate,
    parse_dedup_response,
    parse_extraction_response,
    strip_markdown_fence,
)
from .pipeline import PIPELINE_FLAG_ENV, PipelineDisabledError, run_daily
from .prompts import (
    CONFLICT_DETECTION_SYSTEM_PROMPT,
    EXTRACT_MEMORIES_SYSTEM_PROMPT,
    Material,
    format_batch_dedup_prompt,
    format_extraction_prompt,
)
from .recall import RecallBundle, build_recall_bundle, recall_for_prompt, recall_top_k
from .store import MemoryRecord, MemoryStore, new_record_id

__all__ = [
    "CONFLICT_DETECTION_SYSTEM_PROMPT",
    "DedupDecision",
    "EXTRACT_MEMORIES_SYSTEM_PROMPT",
    "ExtractionResult",
    "Material",
    "MemoryCandidate",
    "MemoryRecord",
    "MemoryStore",
    "OllamaEmbeddingClient",
    "PIPELINE_FLAG_ENV",
    "PipelineDisabledError",
    "RecallBundle",
    "build_recall_bundle",
    "detect_meta_drift",
    "format_batch_dedup_prompt",
    "format_extraction_prompt",
    "new_record_id",
    "parse_dedup_response",
    "parse_extraction_response",
    "recall_for_prompt",
    "recall_top_k",
    "run_daily",
    "strip_markdown_fence",
]
