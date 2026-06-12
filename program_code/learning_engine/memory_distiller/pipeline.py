"""pipeline — L2 記憶蒸餾 daily 管線（run_daily 入口）。

MODULE_NOTE
模塊用途：每日把 agent.l2_calls + learning.demo_residual_alpha_reports（經
  signal_postmortem 內聯分類）蒸餾成結構化記憶寫入 agent.agent_memory。
  流程（PA spec §6）：讀源 → extraction call → 召回 top-5 → dedup call
  （池空短路）→ 執行裁決（單裁決一個事務）→ 補嵌（flag-gated）→ 統計 JSON。
主要類/函數：run_daily()、PipelineDisabledError、PIPELINE_FLAG_ENV。
依賴：同 package prompts/parsing/store/recall（+ 尾端 lazy backfill）、
  learning_engine.signal_postmortem（純函數內聯，G11 首個消費者）。
  conn 與 llm 全部 caller 注入（cron CLI 經 get_local_llm_client() 取得後
  傳入）；本模組 import 時零網路、零 DB 連線。
硬邊界：
  - flag 守在入口：OPENCLAW_L2_MEMORY_PIPELINE != "1" ⇒ 直接回 disabled，
    零 SQL、零 LLM（cron CLI 殼另在連 DB 前先擋一次，雙層 fail-closed）。
  - 兩段差異化 fail 策略（E2 審查重點 2）：extraction 失敗 ⇒ 當日 skip +
    游標不推進（絕不偽造記憶）；dedup 失敗 ⇒ fail-open-to-store。
  - 對 l2_calls / drar 唯讀；寫入唯一目標 = agent.agent_memory（學習平面，
    root principle 7；零 order/lease/live 觸碰）。
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .parsing import (
    DedupDecision,
    MemoryCandidate,
    parse_dedup_response,
    parse_extraction_response,
)
from .prompts import (
    CONFLICT_DETECTION_SYSTEM_PROMPT,
    EXTRACT_MEMORIES_SYSTEM_PROMPT,
    Material,
    format_batch_dedup_prompt,
    format_extraction_prompt,
    truncate_text,
)
from .recall import recall_top_k
from .store import MemoryRecord, MemoryStore, new_record_id

# signal_postmortem：純函數零 DB（G11），learning_engine 內部相對 import。
from ..signal_postmortem import SignalPostmortemEvidence, classify_signal_failure

logger = logging.getLogger(__name__)

# ── flag 家族（全默認 OFF，G19 慣例）────────────────────────────────────────
PIPELINE_FLAG_ENV = "OPENCLAW_L2_MEMORY_PIPELINE"
EMBED_BACKFILL_FLAG_ENV = "OPENCLAW_L2_MEMORY_EMBED_BACKFILL"

# ── 游標 / 輸入 cap（PA spec §6.1 / §6.2 / R5）──────────────────────────────
DATA_DIR_ENV = "OPENCLAW_DATA_DIR"
CURSOR_FILENAME = "l2_memory_distill_cursor.json"
MAX_LOOKBACK_DAYS = 7          # 長期停擺後最多補跑 7 日，防爆量
L2_CALLS_LIMIT = 200           # R5 cap
DRAR_LIMIT = 20
FIELD_TRUNCATE_CHARS = 4096    # 每欄 4KB 截斷

# ── LLM 參數（PA spec §6.3；兩段同參數）─────────────────────────────────────
LLM_TEMPERATURE = 0.1
LLM_MAX_TOKENS = 2000
LLM_TIMEOUT_S = 180.0

_L2_CALLS_SQL = (
    "SELECT l2_reply_id, capability_id, trigger, parsed_output, raw_response, created_at "
    "FROM agent.l2_calls "
    "WHERE created_at >= %s AND created_at < %s "
    "ORDER BY created_at LIMIT %s"
)

_DRAR_SQL = (
    "SELECT report_id, strategy_name, report_jsonb, first_seen_ts "
    "FROM learning.demo_residual_alpha_reports "
    "WHERE first_seen_ts >= %s AND first_seen_ts < %s "
    "ORDER BY first_seen_ts LIMIT %s"
)


class PipelineDisabledError(RuntimeError):
    """target_date 模式下 flag-OFF 的專用例外（E2-A LOW-1 修復輪）。

    為什麼是例外而非回 dict：cron CLI 以「無例外=成功」推進游標；回 disabled
    dict 會讓 CLI 把「根本沒處理」的日子標記成功 ⇒ 該日材料永久丟失。
    自管模式（無 target_date）維持回 dict（caller 無游標紀律依賴）。
    """


def _flag_on(name: str) -> bool:
    """env flag 判定（strip 防尾隨空白/換行）。

    為什麼 strip（E2-A LOW-1）：cron CLI 殼的 gate 已 strip；此處若不 strip，
    env 值 "1 " 會造成 CLI 放行而 pipeline 靜默 disabled 的判定縫。
    """
    return os.getenv(name, "0").strip() == "1"


def _resolve_embed_client(embed_client: Any) -> Any:
    """embed client 解析：顯式注入優先；EMBED_BACKFILL flag=1 時 lazy 構造默認 client。

    為什麼在這裡構造（E2 MED-1 / MIT F-1 雙線同源退回）：OllamaEmbeddingClient
    先前全 repo 零非測試構造點——flag 有 gate 無 functional consumer，embedding
    軸（補嵌 + recall L1 + [89]）整條結構性不可達。建構子只讀 env 不打網路；
    可達性由 is_available() 探測（默認 base = http://127.0.0.1:11434），失敗
    fail-soft：backfill 回 embed_unavailable、recall 降 FTS，絕不 raise。
    """
    if embed_client is not None:
        return embed_client
    if not _flag_on(EMBED_BACKFILL_FLAG_ENV):
        return None
    from .embedding import OllamaEmbeddingClient  # noqa: PLC0415 — flag-ON 才拉依賴

    return OllamaEmbeddingClient()


# ─────────────────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────────────────


def run_daily(
    conn: Any,
    llm: Any,
    *,
    target_date: date | None = None,
    now: datetime | None = None,
    state_path: str | Path | None = None,
    embed_client: Any = None,
) -> dict[str, Any]:
    """蒸餾管線唯一入口（cron CLI 殼以 string import 呼叫，PA spec §14）。

    flag 不為 "1"（strip 後）時在觸碰 conn/llm 之前短路（零副作用）：
    自管模式回 disabled dict；target_date 模式 raise PipelineDisabledError
    （CLI 游標紀律靠例外維持，disabled ≠ 成功）。

    兩種模式（兩線並行合流接縫，缺一不可）：
    - ``target_date`` 提供（cron CLI 模式，E1-B 呼叫形
      ``run_daily(conn, llm, target_date=day)``）：只處理該單日、完全不碰
      游標檔（游標由 CLI 自管）。**當日失敗 raise RuntimeError**——CLI 的
      游標紀律靠例外維持（exception ⇒ 不 write_cursor ⇒ 下輪補跑）；
      回 dict 而不 raise 會讓 CLI 把失敗日誤判成功推進游標（= 違反
      「extraction fail ⇒ 游標不推進」鐵則）。
    - ``target_date`` 缺省（自管模式）：內部讀寫游標檔，處理窗 =
      (cursor+1 日)..(昨日)，上限回看 MAX_LOOKBACK_DAYS；逐日處理，成功日
      立即推進游標，失敗日中止（永不 raise，回統計 dict）。
    """
    if not _flag_on(PIPELINE_FLAG_ENV):
        if target_date is not None:
            raise PipelineDisabledError(
                f"{PIPELINE_FLAG_ENV} != 1 — target_date 模式拒絕執行"
                "（disabled ≠ 成功，防 CLI 誤推游標）"
            )
        return {"status": "disabled", "flag": PIPELINE_FLAG_ENV}

    # embedding 軸活化點（MED-1/F-1）：backfill flag=1 且無顯式注入 ⇒ 構造默認
    # client；同一實例 thread 進 recall L1 與 backfill（兩模式共用本解析）。
    embed_client = _resolve_embed_client(embed_client)

    if target_date is not None:
        return _run_single_day(conn, llm, target_date, embed_client=embed_client)

    now_utc = now or datetime.now(timezone.utc)
    cursor_path = _resolve_cursor_path(state_path)
    if cursor_path is None:
        # 路徑不可解析＝配置錯誤：誠實報 error、零 DB 副作用（cron fail-soft 收斂）。
        return {"status": "error", "error": "cursor_path_unresolved"}

    cursor = _read_cursor(cursor_path)
    days = _compute_window(cursor, now_utc.date())
    day_results: list[dict[str, Any]] = []
    for day in days:
        result = _process_day(conn, llm, day, embed_client=embed_client)
        result["utc_date"] = day.isoformat()
        day_results.append(result)
        if result.get("ok"):
            _write_cursor(cursor_path, day)
        else:
            # 失敗日游標不推進；後續日也不跳過（補跑順序性）。
            logger.warning(
                "l2 memory distill day=%s failed: %s", day, result.get("error")
            )
            break

    backfill: dict[str, Any] | None = None
    if _flag_on(EMBED_BACKFILL_FLAG_ENV):
        # lazy import：補嵌默認 OFF，不為主路徑拉依賴。
        from .backfill_embeddings import run_backfill  # noqa: PLC0415

        backfill = run_backfill(conn, embed_client)

    return {
        "status": "ok",
        "days_attempted": len(day_results),
        "days_succeeded": sum(1 for r in day_results if r.get("ok")),
        "day_results": day_results,
        "backfill": backfill,
    }


def _run_single_day(
    conn: Any, llm: Any, target_date: date, *, embed_client: Any = None
) -> dict[str, Any]:
    """cron CLI 單日模式（游標歸 CLI；失敗 raise 維持 CLI 游標紀律）。"""
    result = _process_day(conn, llm, target_date, embed_client=embed_client)
    result["utc_date"] = target_date.isoformat()
    if not result.get("ok"):
        # 為什麼 raise：CLI 以「無例外=成功」決定 write_cursor；靜默回 dict
        # 會讓失敗日被推進游標、該日材料永久丟失（違 §6.3 游標鐵則）。
        raise RuntimeError(
            f"l2 memory distill day={target_date.isoformat()} failed: "
            f"{result.get('error', 'unknown')}"
        )

    backfill: dict[str, Any] | None = None
    if _flag_on(EMBED_BACKFILL_FLAG_ENV):
        from .backfill_embeddings import run_backfill  # noqa: PLC0415

        backfill = run_backfill(conn, embed_client)

    return {
        "status": "ok",
        "days_attempted": 1,
        "days_succeeded": 1,
        "day_results": [result],
        "backfill": backfill,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 游標
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_cursor_path(state_path: str | Path | None) -> Path | None:
    """游標檔路徑：顯式參數優先；否則 ${OPENCLAW_DATA_DIR}/cron_state/<file>。

    不硬編任何機器路徑（跨平台紅線）；env 缺失且未注入 ⇒ None（caller 報 error）。
    """
    if state_path is not None:
        return Path(state_path)
    data_dir = os.getenv(DATA_DIR_ENV, "").strip()
    if not data_dir:
        return None
    return Path(data_dir) / "cron_state" / CURSOR_FILENAME


def _read_cursor(path: Path) -> date | None:
    """讀游標；檔缺 / JSON 壞 / 日期非法 ⇒ None（視同首跑，只處理昨日）。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return date.fromisoformat(str(payload["last_success_utc_date"]))
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001 — 壞游標不致命，但要可觀測
        logger.warning("l2 memory distill cursor 不可讀（視同首跑）: %s", exc)
        return None


def _write_cursor(path: Path, day: date) -> None:
    """成功日推進游標（mkdir -p 容錯；寫失敗記 log 不拋——下輪重跑冪等）。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"last_success_utc_date": day.isoformat()}),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("l2 memory distill cursor 寫入失敗: %s", exc)


def _compute_window(cursor: date | None, today: date) -> list[date]:
    """處理窗 = (cursor+1)..(昨日)，cap 回看 MAX_LOOKBACK_DAYS。"""
    yesterday = today - timedelta(days=1)
    start = yesterday if cursor is None else cursor + timedelta(days=1)
    floor = yesterday - timedelta(days=MAX_LOOKBACK_DAYS - 1)
    if start < floor:
        start = floor
    if start > yesterday:
        return []
    return [start + timedelta(days=i) for i in range((yesterday - start).days + 1)]


# ─────────────────────────────────────────────────────────────────────────────
# 單日處理
# ─────────────────────────────────────────────────────────────────────────────


def _process_day(
    conn: Any, llm: Any, day: date, *, embed_client: Any = None
) -> dict[str, Any]:
    """處理單一 UTC 日。回 {"ok": bool, ...}；ok=False ⇒ caller 不推進游標。"""
    win_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    win_end = win_start + timedelta(days=1)

    try:
        materials = _build_materials(conn, win_start, win_end)
    except Exception as exc:  # noqa: BLE001 — 讀源失敗=當日失敗（補跑）
        _safe_rollback(conn)
        return {"ok": False, "error": f"source_read_failed: {exc}"}

    # l2 源材料計數（[88] 語義死亡軸：「l2_calls 當日非空但 0 寫入」需要
    # l2-專屬計數，混合 materials 總數無法區分 drar-only 日）。
    materials_l2 = sum(1 for m in materials if m.source_kind == "l2_call")

    if not materials:
        # 兩源皆空 ⇒ 當日 no-op，照常推進游標（PA spec §6.2-3）。
        return {"ok": True, "noop": True, "stored": 0, "materials_l2": 0}

    # ── (1) extraction call ──
    text, success = _call_llm(
        llm, system=EXTRACT_MEMORIES_SYSTEM_PROMPT,
        prompt=format_extraction_prompt(materials),
    )
    if not success:
        return {"ok": False, "error": "extraction_llm_unavailable"}
    extraction = parse_extraction_response(text, [m.material_id for m in materials])
    if not extraction.ok:
        # extraction parse fail ⇒ 當日 skip + 游標不推進（不偽造記憶，§6.3）。
        return {"ok": False, "error": extraction.error}
    if not extraction.memories:
        return {
            "ok": True,
            "stored": 0,
            "dropped": extraction.dropped_count,
            "materials_l2": materials_l2,
        }

    # ── (2) 每條候選召回 top-5 → 統一候選池 ──
    candidates: dict[str, MemoryCandidate] = {
        new_record_id(): cand for cand in extraction.memories
    }
    pool: dict[str, dict[str, Any]] = {}
    related: dict[str, list[str]] = {}
    for rid, cand in candidates.items():
        rows, _level = recall_top_k(conn, cand.content, k=5, embed_client=embed_client)
        related[rid] = [str(r.get("record_id", "")) for r in rows]
        for r in rows:
            pool[str(r.get("record_id", ""))] = r

    # ── (3) dedup call（池全空 ⇒ 跳過 call 直接全 store，省一次 LLM call）──
    rids = list(candidates.keys())
    if not pool:
        decisions: list[DedupDecision] = [
            DedupDecision(record_id=rid, action="store") for rid in rids
        ]
        dedup_called = False
    else:
        dedup_called = True
        new_view = [
            {
                "record_id": rid,
                "content": candidates[rid].content,
                "mem_type": candidates[rid].mem_type,
                "priority": candidates[rid].priority,
            }
            for rid in rids
        ]
        dtext, dok = _call_llm(
            llm, system=CONFLICT_DETECTION_SYSTEM_PROMPT,
            prompt=format_batch_dedup_prompt(new_view, list(pool.values()), related),
        )
        if not dok:
            # dedup 段 LLM 不可用：與壞 JSON 同向 fail-open-to-store（§6.3）。
            logger.warning("dedup LLM 不可用 → 全部 fail-open-to-store")
            decisions = [
                DedupDecision(record_id=rid, action="store", fail_open=True)
                for rid in rids
            ]
        else:
            decisions = parse_dedup_response(dtext, rids, related)

    # ── (4) 執行裁決 ──
    exec_stats = _execute_decisions(conn, decisions, candidates, extraction.scene)
    return {
        "ok": True,
        "materials": len(materials),
        "materials_l2": materials_l2,
        "extracted": len(extraction.memories),
        "dropped": extraction.dropped_count,
        "dedup_called": dedup_called,
        **exec_stats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 輸入源 → 材料塊
# ─────────────────────────────────────────────────────────────────────────────


def _build_materials(conn: Any, win_start: datetime, win_end: datetime) -> list[Material]:
    """讀兩源（皆唯讀 + LIMIT cap）並文本化為材料塊。"""
    materials: list[Material] = []
    cur = conn.cursor()

    # 源 1：agent.l2_calls（唯讀）。
    cur.execute(_L2_CALLS_SQL, (win_start, win_end, L2_CALLS_LIMIT))
    for row in cur.fetchall():
        l2_reply_id, capability_id, trigger, parsed_output, raw_response, created_at = row
        parts = [
            f"capability={capability_id}",
            f"trigger={trigger}",
            "parsed_output=" + truncate_text(_jsonish(parsed_output), FIELD_TRUNCATE_CHARS),
            "raw_response=" + truncate_text(str(raw_response or ""), FIELD_TRUNCATE_CHARS),
        ]
        materials.append(
            Material(
                material_id=f"l2:{l2_reply_id}",
                source_kind="l2_call",
                ts_iso=_iso(created_at),
                text=" | ".join(parts),
            )
        )

    # 源 2：drar（V131）→ signal_postmortem 內聯分類（G11 首個消費者）。
    cur = conn.cursor()
    cur.execute(_DRAR_SQL, (win_start, win_end, DRAR_LIMIT))
    for row in cur.fetchall():
        report_id, strategy_name, report_jsonb, first_seen_ts = row
        try:
            report = _as_mapping(report_jsonb)
            evidence = SignalPostmortemEvidence(
                candidate_id=f"drar:{report_id}",
                family_id=str(strategy_name or "unknown"),
                residual_report=report,
            )
            pm = classify_signal_failure(evidence)
            text = (
                f"strategy={strategy_name} taxonomy={pm.taxonomy} "
                f"confidence={pm.confidence} rationale={truncate_text(pm.rationale, 1024)}"
            )
        except Exception as exc:  # noqa: BLE001 — 單 row 分類失敗不殺整日
            logger.warning("postmortem 分類失敗 report_id=%s: %s", report_id, exc)
            continue
        materials.append(
            Material(
                material_id=f"drar:{report_id}",
                source_kind="drar_postmortem",
                ts_iso=_iso(first_seen_ts),
                text=text,
            )
        )
    return materials


def _jsonish(value: Any) -> str:
    """JSONB 欄位文本化（psycopg2 回 dict；fake/str 原樣）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def _as_mapping(value: Any) -> dict[str, Any] | None:
    """report_jsonb 正規化為 dict；不可解析回 None（postmortem 自身誠實降級）。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


# ─────────────────────────────────────────────────────────────────────────────
# 裁決執行（單裁決一個事務）
# ─────────────────────────────────────────────────────────────────────────────


def _execute_decisions(
    conn: Any,
    decisions: Sequence[DedupDecision],
    candidates: dict[str, MemoryCandidate],
    scene: str,
) -> dict[str, Any]:
    """逐條執行裁決，每條獨立 commit/rollback（部分失敗不污染整批，§6.3-4）。"""
    store = MemoryStore(conn)
    stored = superseded = skipped = failed = fail_open = 0

    for d in decisions:
        cand = candidates.get(d.record_id)
        if cand is None:
            failed += 1
            continue
        try:
            if d.action == "skip":
                skipped += 1
                continue
            if d.action == "store":
                store.insert_record(_record_from_candidate(d.record_id, cand, scene))
                conn.commit()
                stored += 1
                if d.fail_open:
                    fail_open += 1
                continue
            # update / merge：INSERT 新 row（merged 內容）+ supersede 舊 targets。
            old_rows = store.load_candidates_by_ids(list(d.target_ids))
            union_refs = _union_source_refs(
                _refs_from_source_ids(cand.source_ids),
                [ref for row in old_rows for ref in _as_ref_list(row.get("source_refs"))],
            )
            meta = dict(cand.metadata)
            meta["merged_from"] = list(d.target_ids)
            meta["dedup_action"] = d.action
            # origin 由並集 refs 推導（含舊血緣）⇒ untrusted 沿 supersede 鏈傳染。
            meta["origin"] = _origin_for_refs(union_refs)
            event_start, event_end = _parse_event_window(cand.metadata)
            record = MemoryRecord(
                record_id=d.record_id,
                content=d.merged_content,
                mem_type=d.merged_type,
                priority=(
                    d.merged_priority if d.merged_priority is not None else cand.priority
                ),
                scene=scene,
                source_refs=tuple(union_refs),
                event_time_str=cand.event_time_str,
                event_start=event_start,
                event_end=event_end,
                metadata=meta,
            )
            store.insert_record(record)
            n = store.supersede_records(list(d.target_ids), d.record_id)
            conn.commit()
            stored += 1
            superseded += n
        except Exception as exc:  # noqa: BLE001 — 單裁決失敗隔離
            logger.warning("裁決執行失敗 record=%s action=%s: %s", d.record_id, d.action, exc)
            _safe_rollback(conn)
            failed += 1

    return {
        "stored": stored,
        "superseded": superseded,
        "skipped": skipped,
        "failed": failed,
        "fail_open": fail_open,
    }


def _record_from_candidate(
    record_id: str, cand: MemoryCandidate, scene: str
) -> MemoryRecord:
    refs = _refs_from_source_ids(cand.source_ids)
    meta = dict(cand.metadata)
    # 系統擁有鍵：無條件覆蓋（metadata 來自 LLM 輸出，不可讓模型自填 origin
    # 偽裝 curated——E3 MED-2 的圍欄鍵必須由確定性代碼推導）。
    meta["origin"] = _origin_for_refs(refs)
    event_start, event_end = _parse_event_window(cand.metadata)
    return MemoryRecord(
        record_id=record_id,
        content=cand.content,
        mem_type=cand.mem_type,
        priority=cand.priority,
        scene=scene,
        source_refs=tuple(refs),
        event_time_str=cand.event_time_str,
        event_start=event_start,
        event_end=event_end,
        metadata=meta,
    )


def _origin_for_refs(refs: Sequence[Mapping[str, Any]]) -> str:
    """untrusted 譜系標記（E3 MED-2）：任一 source ref 出自 l2_calls ⇒ l2_untrusted。

    為什麼按 ref kind 推導：l2_calls 材料塊必含 raw_response / parsed_output
    （皆雲端模型自由輸出 = prompt-injection 面），故 kind='l2_call' 即 untrusted；
    drar/lesson/memory_topic 來自本系統確定性 gate/人寫內容 = curated。merge 用
    並集 refs 推導 ⇒ 污染單向傳染、不可被稀釋。B3 未來憑此鍵圍欄注入面。
    """
    if any(ref.get("kind") == "l2_call" for ref in refs):
        return "l2_untrusted"
    return "l2_curated"


def _parse_event_window(
    metadata: Mapping[str, Any],
) -> tuple[datetime | None, datetime | None]:
    """metadata activity_start_time / activity_end_time（ISO 8601）→ typed 事件窗。

    E2-A LOW-2 修復輪：extraction prompt 已要求 LLM 在 metadata 填 ISO 時間，
    此處最小接通 V139 event_start/event_end（可解析才填，否則留 NULL——時間欄
    是可選增強，解析失敗不丟記憶也不污染 typed 欄）。naive datetime 視為 UTC
    （材料 ts 全 UTC）；反向區間（end < start）= LLM 時間幻覺 ⇒ 雙雙留 NULL
    （原話仍存於 metadata 字串，不丟證據）。
    """
    start = _parse_event_ts(metadata.get("activity_start_time"))
    end = _parse_event_ts(metadata.get("activity_end_time"))
    if start is not None and end is not None and end < start:
        return None, None
    return start, end


def _parse_event_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        # 'Z' 後綴正規化為 +00:00（防舊 runtime fromisoformat 差異）。
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _refs_from_source_ids(source_ids: Sequence[str]) -> list[dict[str, Any]]:
    """材料 id → source_refs 映射（PA spec §5.1 id 規則的逆向）。"""
    refs: list[dict[str, Any]] = []
    for sid in source_ids:
        if sid.startswith("l2:"):
            refs.append({"kind": "l2_call", "id": sid[len("l2:"):]})
        elif sid.startswith("drar:"):
            raw = sid[len("drar:"):]
            refs.append({"kind": "drar", "id": int(raw) if raw.isdigit() else raw})
        else:
            refs.append({"kind": "unknown", "id": sid})
    return refs


def _as_ref_list(value: Any) -> list[dict[str, Any]]:
    """舊 row source_refs JSONB 正規化（psycopg2 回 list；fake/str 容錯）。"""
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [v for v in parsed if isinstance(v, dict)] if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _union_source_refs(
    new_refs: list[dict[str, Any]], old_refs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """新∪舊 source_refs 並集（merge 血緣保全，§6.3-4）；以確定性序列化鍵去重。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for ref in [*new_refs, *old_refs]:
        key = json.dumps(ref, sort_keys=True, ensure_ascii=False, default=str)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# LLM 適配
# ─────────────────────────────────────────────────────────────────────────────


def _call_llm(llm: Any, *, system: str, prompt: str) -> tuple[str, bool]:
    """單發 LLM call 薄適配。

    為什麼要內省 timeout 參數名：get_local_llm_client() 回傳的 OllamaClient
    用 ``timeout=``（秒，int），而 LocalLLMClient ABC 用 ``timeout_s=``——
    兩 surface 並存（spec G7 引 ABC，工廠實際回 OllamaClient）。按簽名擇一，
    都沒有則不傳（用 client 預設）。
    回 (text, success)；任何例外 ⇒ ("", False)（caller 按段內 fail 策略處理）。
    """
    kwargs: dict[str, Any] = {
        "system": system,
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
    }
    try:
        params = inspect.signature(llm.generate).parameters
        if "timeout_s" in params:
            kwargs["timeout_s"] = LLM_TIMEOUT_S
        elif "timeout" in params:
            kwargs["timeout"] = int(LLM_TIMEOUT_S)
    except (TypeError, ValueError):
        pass  # 簽名不可內省（C 擴展/Mock）：不傳 timeout，用 client 預設
    try:
        resp = llm.generate(prompt, **kwargs)
    except Exception as exc:  # noqa: BLE001 — LLM 例外不冒泡，回失敗
        logger.warning("LLM call 失敗: %s", exc)
        return "", False
    text = str(getattr(resp, "text", "") or "")
    success = bool(getattr(resp, "success", True)) and bool(text.strip())
    return text, success


def _safe_rollback(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception:  # noqa: BLE001
        pass
