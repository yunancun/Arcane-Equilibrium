from __future__ import annotations

"""
MODULE_NOTE (中文):
  模塊用途：Layer 2 Reflexion critic + 教訓索引庫（lesson store）的純邏輯層。
    1. should_skip_critic — 決定本次 tool 結果是否值得花一次 LLM 做 critic（省成本）。
    2. run_critic         — 對 agent 當前進展做「continue / replan / stop」三態判定，
                            只發一次最便宜 tier 的 LLM 呼叫，嚴格 JSON、偏向 continue。
    3. retrieve_lessons   — 依 symbol + context_hint 以 pg_trgm 相似度撈回過往教訓。
    4. persist_lessons    — 把 session 的 insight 落為 agent.lessons row（唯一寫入口）。

  主要類/函數：CriticResult、should_skip_critic、run_critic、retrieve_lessons、
    persist_lessons。

  依賴：layer2_types（CriticVerdict / env-gate 常量）、db_pool（PG 連接池）、
    layer2_tools_g3_07.is_tool_enabled（沿用 fail-closed 的 truthy env-gate 語意）。
    LLM 呼叫與記帳一律透過傳入的 engine 物件（engine._provider_complete /
    engine._resolve_effective_provider / engine._cost_tracker.record_claude_cost），
    不自建 provider 路由、不重造預算守衛。

  硬邊界：
    - 本模塊不得 import layer2_tools 或 layer2_engine（避免循環 import）。
    - critic 不可下單、不可改 lease / 風控 / 授權；最多只「追加一則訊息」或
      「把 session 收斂為 COMPLETED」，由 engine 端執行。
    - 唯一 DB 寫入是 persist_lessons 的單條 agent.lessons INSERT；其餘皆唯讀。
    - 任何失敗（LLM 不可用 / 超時 / 非 JSON / DB 不可用）一律 fail-soft：
      critic 退回 CONTINUE，retrieve 回空 list，persist 靜默放棄。NEVER raise
      進 agent 迴圈。
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from .layer2_types import (
    CRITIC_VERDICT_CONTINUE,
    CRITIC_VERDICT_REPLAN,
    CRITIC_VERDICT_STOP,
    CRITIC_VERDICT_VALID,
    ENV_L2_CRITIC_ENABLED,
    MODEL_HAIKU,
    TOOL_RECORD_INSIGHT,
    TOOL_SUBMIT_RECOMMENDATION,
    Layer2Config,
    Layer2Session,
)
from . import db_pool
# 沿用 G3-07 的 truthy env-gate helper：與工具旗標完全一致的 fail-closed 語意
# （只有 {"1","true","yes","on"} 視為開啟，未設 / 空字串一律關閉）。
# 為什麼從 g3_07 而非 layer2_tools import：g3_07 只依賴 layer2_types + stdlib，
# 不會把 layer2_tools / layer2_engine 拉進來，故無循環 import 風險。
from .layer2_tools_g3_07 import is_tool_enabled

logger = logging.getLogger(__name__)


# pg_trgm 相似度門檻：retrieve_lessons 的 `content % $hint` 用此值，不用 session 預設。
# 為什麼降到 0.1：pg_trgm 的 `%` 運算子預設門檻 pg_trgm.similarity_threshold = 0.3。
# MIT 在 V133 Linux PG 實證（dry-run）量到真正相關的教訓 similarity 僅 0.2785 / 0.2647，
# 兩者皆 < 0.3，導致 `%` 查詢回 0 列、retrieve_lessons 靜默落到 recency-only 兜底，
# 等於整個 trigram 相似度檢索（gin 索引 idx_agent_lessons_content_trgm）形同虛設。
# 故在相似度查詢前以 SET LOCAL 把門檻降到 0.1（交易短語 trigram 重疊本就稀疏）。
# SET LOCAL 為交易內作用域，put_conn 歸還前又會 rollback，不會污染 pool 內連線。
LESSON_TRGM_MIN_SIM = 0.1


# ─────────────────────────────────────────────────────────
# 結果型別
# ─────────────────────────────────────────────────────────

@dataclass
class CriticResult:
    """
    critic 對「是否繼續推理」的判定。

    verdict ∈ CRITIC_VERDICT_VALID（continue / replan / stop）。
    reason 為簡短理由（replan 時會被引擎接成 user 訊息；其餘僅供 debug / 記錄）。
    任何不確定都回 CriticResult(CONTINUE)，符合 fail-soft 預設。
    """
    verdict: str = CRITIC_VERDICT_CONTINUE
    reason: str = ""


# ─────────────────────────────────────────────────────────
# 同一輪多 tool call 的 critic verdict 聚合：取「最嚴重」
# ─────────────────────────────────────────────────────────

# 嚴重度排序（數字越大越嚴重）：stop > replan > continue。
# 為什麼以最嚴重為準而非 last-wins：同一輪若有多個 tool call，其中之一 critic
# 判 STOP（煞車）但後續 tool 判 CONTINUE，last-wins 會把 STOP 蓋掉而錯失煞車，
# 形成「漏煞車」的安全缺口。聚合必須讓最嚴重的判定勝出，與保守 fail-safe 一致。
_CRITIC_SEVERITY: dict[str, int] = {
    CRITIC_VERDICT_CONTINUE: 0,
    CRITIC_VERDICT_REPLAN: 1,
    CRITIC_VERDICT_STOP: 2,
}


def merge_critic_verdict(
    current: CriticResult | None,
    incoming: CriticResult | None,
) -> CriticResult | None:
    """
    把本輪內逐 tool 的 critic 判定聚合為「最嚴重」者。

    規則：
      - 任一方為 None → 回另一方（None 代表「該 tool 未跑 critic / 無意見」，
        不參與嚴重度比較，也不會把已存在的判定降級）。
      - 兩者皆非 None → 回嚴重度較高者；嚴重度相等時保留 current（穩定、不抖動）。
      - 嚴重度排序：stop(2) > replan(1) > continue(0)；未知 verdict 視為最不嚴重（-1），
        不會壓過任何有效判定（防呆，理論上不會發生）。

    為什麼抽成純函式：讓「最嚴重聚合」可被獨立單測（mutation 可咬住），
    引擎迴圈只負責呼叫，不把分支判斷散落在熱路徑裡。
    """
    if current is None:
        return incoming
    if incoming is None:
        return current
    cur_rank = _CRITIC_SEVERITY.get(current.verdict, -1)
    inc_rank = _CRITIC_SEVERITY.get(incoming.verdict, -1)
    return incoming if inc_rank > cur_rank else current


# ─────────────────────────────────────────────────────────
# critic system prompt（嚴格 JSON、強烈偏向 continue）
# ─────────────────────────────────────────────────────────

# 為什麼偏向 continue：critic 是輔助煞車而非主導者。誤殺一個正在收斂的
# session 比多跑一兩輪更糟（成本由既有 session/daily budget 守衛兜底）。
# 只有在明確「打轉 / 偏題 / 已可結論」時才 replan / stop。
_CRITIC_SYSTEM_PROMPT = (
    "You are a terse reasoning critic for a crypto trading analysis agent. "
    "Given the agent's latest tool call and its result, decide whether the agent "
    "should keep going. Strongly bias toward 'continue'. Only choose 'replan' if "
    "the agent is clearly looping, going off-topic, or ignoring an error in the "
    "result; only choose 'stop' if the result already makes the conclusion obvious "
    "and further tool calls would waste money.\n"
    "Respond with ONLY a compact JSON object, no prose:\n"
    '{"verdict": "continue|replan|stop", "reason": "<=15 words"}'
)


# ─────────────────────────────────────────────────────────
# critic：是否跳過（省 LLM 成本的前置過濾）
# ─────────────────────────────────────────────────────────

def should_skip_critic(
    tool_name: str,
    result_str: str,
    session: Layer2Session,
    config: Layer2Config,
) -> bool:
    """
    判斷是否「跳過 critic」（不發 LLM）。回 True = 跳過。

    跳過條件（任一成立即跳過）：
      - critic 旗標未開（OPENCLAW_L2_CRITIC_ENABLED 非 truthy）→ 預設關閉。
      - 工具是 submit_recommendation / record_insight：這兩個是「收尾動作」，
        對其結果做 critic 無意義（agent 已表態）。
      - 工具結果含 "error"：錯誤分支讓 agent 自己在下一輪看到並處理，
        不值得額外 LLM。
      - 目前累計 tool 呼叫 < 2：太早，沒有足夠進展可評。
      - 已到倒數第二輪（iteration >= max_iterations - 1）：再 replan 也無迭代
        空間，徒增成本。

    為什麼旗標放最前面短路：旗標關閉時必須完全不碰其他判斷，確保
    flags-OFF 行為與原碼 byte-identical。
    """
    if not is_tool_enabled(ENV_L2_CRITIC_ENABLED):
        return True
    if tool_name in (TOOL_SUBMIT_RECOMMENDATION, TOOL_RECORD_INSIGHT):
        return True
    # 不分大小寫地偵測 "error"，與工具 fail-soft 回傳的 error 欄位語意一致。
    if "error" in (result_str or "").lower():
        return True
    if len(session.tool_calls) < 2:
        return True
    # session.iterations 為 1-based（引擎設為 iteration+1）；config.max_iterations
    # 為迴圈上限。到達倒數第二輪後再 replan 已無意義。
    if session.iterations >= max(config.max_iterations - 1, 0):
        return True
    return False


# ─────────────────────────────────────────────────────────
# critic：單次 LLM 判定
# ─────────────────────────────────────────────────────────

async def run_critic(
    engine: Any,
    session: Layer2Session,
    tool_name: str,
    tool_input: dict[str, Any],
    result_str: str,
) -> CriticResult:
    """
    對 agent 當前進展做一次 critic 判定，回 CriticResult。

    成本與路由：透過 engine 既有設施，不自建。
      - engine._resolve_effective_provider(role="triage") → 強制最便宜 tier。
      - engine._provider_complete(...) → asyncio-friendly + fail-soft（回 None）。
      - engine._cost_tracker.record_claude_cost(...) → 計入 session/daily 預算。

    不變量 / fail-soft：
      - max_tokens≈128：critic 只需一個短 JSON。
      - 任何失敗（provider 不可用 / 超時 / 回 None / 非 JSON / verdict 非法）
        → 回 CriticResult(CONTINUE)。NEVER raise。
      - 不發第二次呼叫、不重試（重試屬交易效果以外的成本放大，避免）。
    """
    try:
        # 動態 import provider_client，避免模塊載入期耦合；引擎已用同一模塊。
        from . import provider_client as _pc

        config = engine._cost_tracker.get_config()
        base_provider = config.default_provider or _pc.PROVIDER_ANTHROPIC
        # triage role → 強制該 provider 最便宜 tier（Haiku-equiv）。
        eff_provider, eff_tier = engine._resolve_effective_provider(
            base_provider=base_provider,
            base_tier=MODEL_HAIKU,
            role="triage",
        )

        critic_input = (
            f"Tool called: {tool_name}\n"
            f"Tool input: {json.dumps(tool_input, ensure_ascii=False)[:500]}\n"
            f"Tool result (truncated):\n{(result_str or '')[:1500]}"
        )

        response = await engine._provider_complete(
            provider_name=eff_provider,
            tier=eff_tier,
            system_prompt=_CRITIC_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": critic_input}],
            tools=None,
            max_tokens=128,
            timeout=30.0,
        )
        if response is None:
            return CriticResult(CRITIC_VERDICT_CONTINUE, "critic provider unavailable")

        # 記帳：用 effective tier_key 走既有預算管線（pricing 缺條目時不致命）。
        try:
            engine._cost_tracker.record_claude_cost(
                session, response.input_tokens, response.output_tokens, eff_tier,
            )
        except KeyError:
            logger.warning("critic tier %s 不在 pricing table，cost 未計入", eff_tier)

        try:
            parsed = json.loads(response.text or "{}")
        except (json.JSONDecodeError, TypeError):
            return CriticResult(CRITIC_VERDICT_CONTINUE, "critic non-JSON response")

        verdict = parsed.get("verdict")
        if verdict not in CRITIC_VERDICT_VALID:
            return CriticResult(CRITIC_VERDICT_CONTINUE, "critic verdict invalid")

        reason = str(parsed.get("reason", ""))[:200]
        if verdict == CRITIC_VERDICT_REPLAN:
            return CriticResult(CRITIC_VERDICT_REPLAN, reason or "replan suggested")
        if verdict == CRITIC_VERDICT_STOP:
            return CriticResult(CRITIC_VERDICT_STOP, reason or "stop suggested")
        return CriticResult(CRITIC_VERDICT_CONTINUE, reason)

    except Exception as exc:  # noqa: BLE001 — critic 必須 fail-soft，不得拋進迴圈
        logger.warning("run_critic fail-soft → continue: %s", exc)
        return CriticResult(CRITIC_VERDICT_CONTINUE, "critic exception")


# ─────────────────────────────────────────────────────────
# lesson store：檢索（唯讀）
# ─────────────────────────────────────────────────────────

async def retrieve_lessons(
    symbol: str,
    context_hint: str,
    lesson_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    依 symbol + context_hint 撈回最相關的數條過往教訓（最多 5）。

    檢索策略：
      - 優先 pg_trgm 相似度：以 SET LOCAL 把門檻降到 LESSON_TRGM_MIN_SIM 後，
        content % $hint 過濾再 similarity(content,$hint) DESC（門檻不用 0.3 預設，
        否則真正相關教訓 similarity≈0.27 會被擋掉，見該常數註解）。
      - 若 pg_trgm 不可用 / 相似度查詢回空 / 任何 DB 例外 → recency-only 兜底
        （created_at DESC）。
      - symbol 一律過濾；lesson_type 提供時加過濾。

    同步 PG 讀取包進 asyncio.to_thread，避免阻塞事件迴圈。
    任何失敗回空 list，NEVER raise。
    """
    sym = (symbol or "").strip()
    hint = (context_hint or "").strip()
    if not sym:
        return []
    try:
        return await asyncio.to_thread(_retrieve_lessons_sync, sym, hint, lesson_type)
    except Exception as exc:  # noqa: BLE001 — fail-soft：撈不到就當沒有教訓
        logger.warning("retrieve_lessons fail-soft → []: %s", exc)
        return []


def _retrieve_lessons_sync(
    symbol: str,
    context_hint: str,
    lesson_type: str | None,
) -> list[dict[str, Any]]:
    """同步 PG 檢索 helper（DB 不可用回 []，不 raise）。"""
    with db_pool.get_pg_conn() as conn:
        if conn is None:
            return []
        # lesson_type 過濾片段（綁定參數，非字串拼接）。
        type_clause = "AND lesson_type = %s" if lesson_type else ""

        # 先試 trigram 相似度檢索。context_hint 為空則直接走 recency 分支。
        if context_hint:
            # 保留 `content % $hint`（命中 gin 索引 idx_agent_lessons_content_trgm），
            # 但用 SET LOCAL 把門檻從 pg_trgm 預設 0.3 降到 LESSON_TRGM_MIN_SIM（0.1）。
            # 為什麼必須降：MIT 實證真正相關教訓 similarity ≈ 0.27 < 0.3，預設門檻下
            # `%` 回 0 列、整個相似度檢索失效（見模塊頂常數註解）。
            sql = (
                "SELECT id, created_at, symbol, lesson_type, content, "
                "       session_trigger, context_id, source "
                "FROM agent.lessons "
                "WHERE symbol = %s "
                f"  {type_clause} "
                "  AND content %% %s "
                "ORDER BY similarity(content, %s) DESC "
                "LIMIT 5"
            )
            params: tuple[Any, ...]
            if lesson_type:
                params = (symbol, lesson_type, context_hint, context_hint)
            else:
                params = (symbol, context_hint, context_hint)
            try:
                cur = conn.cursor()
                # SET LOCAL 為交易內作用域：put_conn 歸還連線前一律 rollback，
                # 門檻不會洩漏到 pool 內其他借用者；且 `%` 仍走 gin 索引。
                cur.execute(
                    "SET LOCAL pg_trgm.similarity_threshold = %s",
                    (LESSON_TRGM_MIN_SIM,),
                )
                cur.execute(sql, params)
                rows = _rows_to_dicts(cur)
                if rows:
                    return rows
            except Exception as exc:  # noqa: BLE001 — pg_trgm 缺失 / 語法不支援 → 兜底
                # 相似度查詢失敗（多半是 pg_trgm 未裝或 % 運算子不可用）；
                # rollback 後改走 recency-only，確保仍能回最新教訓。
                logger.info("retrieve_lessons trgm 不可用，改 recency: %s", exc)
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass

        # recency-only 兜底（trgm 不可用 / 無相似命中 / hint 為空）。
        recency_sql = (
            "SELECT id, created_at, symbol, lesson_type, content, "
            "       session_trigger, context_id, source "
            "FROM agent.lessons "
            "WHERE symbol = %s "
            f"  {type_clause} "
            "ORDER BY created_at DESC "
            "LIMIT 5"
        )
        recency_params: tuple[Any, ...]
        if lesson_type:
            recency_params = (symbol, lesson_type)
        else:
            recency_params = (symbol,)
        cur = conn.cursor()
        cur.execute(recency_sql, recency_params)
        return _rows_to_dicts(cur)


def _rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    """把 cursor 結果轉為 dict list（欄位順序與 SELECT 對齊）。"""
    cols = [d[0] for d in cur.description]
    out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        out.append(dict(zip(cols, row)))
    return out


# ─────────────────────────────────────────────────────────
# lesson store：寫入（唯一 DB 寫入口）
# ─────────────────────────────────────────────────────────

async def persist_lessons(
    insights: list[Any],
    session: Layer2Session,
    symbol: str,
) -> None:
    """
    把本 session 的 insight 落為 agent.lessons row（唯一 DB 寫入口）。

    偏離 PA 簽名說明：PA 給的簽名為 persist_lessons(insights, session)，但
    agent.lessons.symbol 為 NOT NULL，而 Layer2Session 無 symbol 欄位（symbol
    僅在 run_session 參數中）。故補一個 symbol 參數，由引擎 hook 處（symbol
    在作用域內）傳入。其餘語意不變。

    寫入欄位：
      - symbol：本 session 分析標的（NOT NULL）。
      - lesson_type：取自 insight.category（無則 'general'）。
      - content：insight 標題 + 細節摘要。
      - session_trigger：session.trigger。
      - context_id：session.session_id（可用且可追溯；非 strategy:symbol）。
      - outcome_net_bps：永遠 NULL（forward-stub，decision_outcomes 100% NULL 已知 bug）。
      - session_cost_usd：session.total_cost()。
      - source 走預設 'l2_session'。

    同步 INSERT 包進 asyncio.to_thread；無 insight 直接返回；任何失敗靜默放棄，
    NEVER raise（寫不進教訓庫不得影響 session 收尾）。
    """
    if not insights:
        return
    try:
        await asyncio.to_thread(_persist_lessons_sync, insights, session, symbol)
    except Exception as exc:  # noqa: BLE001 — fail-soft：寫不進不得拋
        logger.warning("persist_lessons fail-soft（放棄寫入）: %s", exc)


def _persist_lessons_sync(
    insights: list[Any],
    session: Layer2Session,
    symbol: str,
) -> None:
    """同步批量 INSERT helper（DB 不可用直接返回，不 raise）。"""
    sym = (symbol or "").strip()
    if not sym:
        return

    session_trigger = getattr(session, "trigger", None)
    context_id = getattr(session, "session_id", None)
    try:
        session_cost = float(session.total_cost())
    except Exception:  # noqa: BLE001
        session_cost = None

    rows: list[tuple[Any, ...]] = []
    for ins in insights:
        category = (getattr(ins, "category", "") or "").strip() or "general"
        title = (getattr(ins, "title", "") or "").strip()
        detail = (getattr(ins, "detail", "") or "").strip()
        content = (f"{title}: {detail}" if title else detail).strip()
        if not content:
            # 無內容的 insight 不落庫（content 為 NOT NULL）。
            continue
        rows.append((
            sym,
            category,
            content[:4000],
            session_trigger,
            context_id,
            None,            # outcome_net_bps：forward-stub，恆 NULL
            session_cost,
        ))

    if not rows:
        return

    with db_pool.get_pg_conn() as conn:
        if conn is None:
            return
        try:
            cur = conn.cursor()
            # 唯一 DB 寫入：參數化 INSERT（symbol/content 等皆綁定參數）。
            # source 用 column DEFAULT 'l2_session'，不在此顯式寫入。
            cur.executemany(
                """
                INSERT INTO agent.lessons
                    (symbol, lesson_type, content, session_trigger,
                     context_id, outcome_net_bps, session_cost_usd)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
            conn.commit()
        except Exception:
            # 寫入失敗則 rollback；外層 to_thread 包裝會被 persist_lessons 吞掉。
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            raise
