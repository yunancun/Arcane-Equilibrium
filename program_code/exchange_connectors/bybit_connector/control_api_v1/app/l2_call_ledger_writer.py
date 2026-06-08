"""
MODULE_NOTE
模塊用途：
  L2 Advisory Mesh D3 取證帳本「唯一 sanctioned 寫入口」（PA 設計 §F）。把單次
  L2 模型呼叫落庫到 agent.l2_calls（V134），並提供 append-only 寫入口給
  agent.l2_consequential_marks（V134 side-table）與 learning.l2_gate_seam_log
  （V135）。全部 INSERT-only。

  現況 D3 中心缺口：layer2_engine 把 system_prompt 餵模型卻從不持久化完整
  prompt/response（PA §0 file:line 已核實）。本 writer 補上 reconstructable
  取證帳本，並在 INSERT 之前跑消毒（hybrid：l2_secret_redactor 掃 secret-pattern
  + error_sanitize 解 str(e)→classified code），sha256 算在已消毒文本上。

主要類/函數：
  - L2CallLedgerWriter：process-global singleton（module-level binding）。
      * record_l2_call(...)          —— 落 agent.l2_calls 一列（消毒在 INSERT 前）。
      * record_consequential_mark(...) —— 落 agent.l2_consequential_marks（事後 mark）。
      * record_gate_seam(...)        —— 落 learning.l2_gate_seam_log。
  - get_l2_call_ledger_writer()：取 singleton（首次 lazy 構造）。

依賴：
  - db_pool.get_pg_conn（psycopg2 ThreadedConnectionPool；persist_lessons 同源）。
  - l2_secret_redactor（secret-pattern 消毒 + 版本）。
  - error_sanitize（str(e)→classified reason_code，錯誤半部）。
  - bybit_ai_invocation_ledger._sha256_text（既有 sha256 helper，不複製第三份）。

硬邊界：
  - INSERT-only：本 writer 對三表「永不 UPDATE / DELETE」。consequential 事後發現
    = marks 表新 INSERT（非 ledger UPDATE）；consequential_at_creation 由 ledger
    INSERT set-once（registry 預設），永不 mutate。對齊 V134 DB-level append-only。
  - 消毒在寫入路徑、INSERT 之前、無窗口：任何 large-text 欄（system_prompt /
    input_context / raw_response / final_summary）絕不以未消毒形落 durable store
    （CLAUDE §四 signed-auth material never leak；root principle 8 reconstructable）。
  - sha256 算在「已消毒」文本上（prompt_sha256 / response_sha256），不是原文——
    否則 hash 與 stored row 不符（PA 設計 E2-must-scrutinize point 2）。
  - 純 audit/provenance：本模塊 import 無 order surface / 無 IntentProcessor /
    無 lease-acquire-for-trading；不授權任何 live 行為。
  - DB 不可用 / psycopg2 缺 → fail-soft（回 ok=False 但 NEVER raise）：D3 寫失敗
    不得阻斷 L2 session 收尾（lineage gap 由 health_monitoring 後續觀測，非崩潰）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from . import db_pool
from . import l2_secret_redactor as _redactor
from . import error_sanitize as _errsan

logger = logging.getLogger("l2_call_ledger_writer")

# 復用既有 sha256 helper（不複製第三份實作）。
try:  # pragma: no cover - import 路徑在 runtime 與 test 皆可用
    from program_code.ai_agents.bybit_thought_gate.bybit_ai_invocation_ledger import (
        _sha256_text as _sha256,
    )
except Exception as _sha_import_exc:  # noqa: BLE001 — 退化到本地等價實作（與 ledger helper 行為一致）
    import hashlib

    # 為何 log WARNING：兩處 sha256 實作理論上恆一致（皆 sha256 hex of utf-8），但
    # 若 import 路徑漂移（套件重構 / sys.path 差異）而靜默走 fallback，未來任一邊改了
    # hash 慣例（如加 "sha256:" 前綴）就會與 ledger 既有 row 對不上而無人察覺。出聲讓
    # 部署期可見此分歧風險（D3 hash 是 reconstructable 不變式的一環）。
    logger.warning(
        "l2_call_ledger_writer 無法 import bybit_ai_invocation_ledger._sha256_text，"
        "退化到本地等價 sha256 實作（驗證 hash 慣例一致）：%s",
        _sha_import_exc,
    )

    def _sha256(text: str | None) -> str | None:  # type: ignore[misc]
        if not text:
            return None
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _to_jsonb_str(obj: object) -> str:
    """把 dict/list 序列化成 psycopg2 可寫進 jsonb 欄的字串（已消毒後呼叫）。"""
    return json.dumps(obj, ensure_ascii=False, default=str)


def _attach_meta(ctx: object, key: str, value: str) -> dict[str, Any]:
    """把一則 metadata（已消毒）附進 input_context，回新 dict（不就地改）。

    為何規範化：input_context 在 P1 reachable 路徑恆為 dict，但簽名容許 list
    （forward-compat）。若直接 `ctx[key]=value` 在 list 上會丟（dict-only 分支），
    導致 _final_summary / _error_reason 靜默消失。此處非-dict 的 ctx 先包成
    {"_context": ctx} 再附 key，保證 metadata 永不遺失（latent 保險）。
    """
    if isinstance(ctx, dict):
        out = dict(ctx)
    else:
        out = {"_context": ctx}
    out[key] = value
    return out


class L2CallLedgerWriter:
    """D3 取證帳本唯一 sanctioned 寫入口（INSERT-only，全部消毒在 INSERT 前）。

    為什麼是 singleton：root principle 1「single controlled write entry」——任何想
    持久化 L2 prompt/response/summary 的模塊都必須經此 writer，不得各自直寫，
    否則消毒窗口與 append-only 不變式會被旁路。
    """

    def __init__(self, *, conn_provider: Any = None) -> None:
        # conn_provider 僅供測試注入（contextmanager → conn）；預設用共享 pool。
        self._conn_provider = conn_provider or db_pool.get_pg_conn

    # ── 公共寫入口 ────────────────────────────────────────────────

    def record_l2_call(
        self,
        *,
        l2_reply_id: str,
        capability_id: str,
        trigger: str,
        created_at: Any,
        model: str,
        contract_ver: str,
        schema_ver: str,
        system_prompt: str,
        input_context: dict[str, Any] | list[Any],
        raw_response: str,
        session_id: str | None = None,
        model_version: str | None = None,
        parsed_output: dict[str, Any] | None = None,
        guard_verdict: str | None = None,
        fact_inf_assm: dict[str, Any] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        latency_ms: int | None = None,
        consequential_at_creation: bool = False,
        final_summary: str | None = None,
        error: BaseException | None = None,
        error_reason_code: str = "internal_error",
    ) -> dict[str, Any]:
        """落 agent.l2_calls 一列。消毒在 INSERT 之前跑、sha256 算在已消毒文本上。

        回 dict：{ok: bool, ledger_state: str, l2_reply_id: str, errors: list[str]}。
        DB 不可用 → ok=False 但不 raise（D3 寫失敗不阻斷 session 收尾）。

        消毒順序（寫入路徑無窗口）：
          1. system_prompt / raw_response / final_summary 過 l2_secret_redactor.redact。
          2. input_context（JSONB）遞迴消毒所有 string leaf。
          3. error → error_sanitize 解 classified (error_code, sanitized_reason)；
             str(e) 絕不 verbatim 落庫（sanitized_reason 也再過 secret redactor 防雙重洩漏）。
          4. prompt_sha256 / response_sha256 = sha256(已消毒 system_prompt / raw_response)。
          5. INSERT。
        """
        result: dict[str, Any] = {
            "ok": True,
            "ledger_state": "l2_call_ledger_recorded",
            "l2_reply_id": l2_reply_id,
            "errors": [],
            "redactor_version": _redactor.REDACTOR_VERSION,
        }

        # ── Step 1-2：消毒所有 large-text 欄（INSERT 之前，無窗口）──
        sp_red = _redactor.redact(system_prompt)
        rr_red = _redactor.redact(raw_response)
        sanitized_prompt = sp_red.text
        sanitized_response = rr_red.text
        sanitized_input_context = _redactor.redact_jsonb(input_context or {})
        sanitized_parsed = (
            _redactor.redact_jsonb(parsed_output) if parsed_output is not None else None
        )
        sanitized_fia = (
            _redactor.redact_jsonb(fact_inf_assm) if fact_inf_assm is not None else None
        )

        # final_summary 若要落庫，併入 input_context 的消毒範圍（D.1.1「applies everywhere」）。
        # input_context 在 P1 reachable 路徑恆為 dict（layer2_engine 傳 {"messages":...}）；
        # 但簽名容許 list（forward-compat）。為避免 list 時 metadata 被靜默丟，先把非-dict
        # 的 context 規範化進 {"_context": <list>} 再附 metadata（latent 保險，不改 dict 行為）。
        if final_summary:
            fs_red = _redactor.redact(final_summary)
            sanitized_input_context = _attach_meta(
                sanitized_input_context, "_final_summary", fs_red.text
            )

        # ── Step 3：錯誤半部 → classified code + sanitized reason（str(e) 絕不 verbatim）──
        error_code: str | None = None
        if error is not None:
            detail = _errsan.sanitize_exc_for_detail(error, reason_code=error_reason_code)
            error_code = (detail.get("reason_codes") or [error_reason_code])[0]
            # sanitized reason 再過 secret redactor（OPENCLAW_DEBUG 模式會夾 truncated str(e)）。
            safe_reason = _redactor.redact(str(detail.get("detail", ""))).text
            sanitized_input_context = _attach_meta(
                sanitized_input_context, "_error_reason", safe_reason
            )

        # ── Step 4：sha256 算在「已消毒」文本上（非原文）──
        prompt_sha256 = _sha256(sanitized_prompt)
        response_sha256 = _sha256(sanitized_response)

        # ── Step 5：INSERT（參數化；jsonb 欄序列化已消毒結構）──
        try:
            with self._conn_provider() as conn:
                if conn is None:
                    result["ok"] = False
                    result["ledger_state"] = "l2_call_ledger_skipped_db_unavailable"
                    result["errors"].append("db_unavailable")
                    return result
                try:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO agent.l2_calls (
                            l2_reply_id, session_id, capability_id, trigger, created_at,
                            model, model_version, contract_ver, schema_ver,
                            system_prompt, input_context, raw_response, parsed_output,
                            guard_verdict, fact_inf_assm, input_tokens, output_tokens,
                            cost_usd, latency_ms, prompt_sha256, response_sha256,
                            redactor_version, error_code, consequential_at_creation
                        )
                        VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s
                        )
                        -- ON CONFLICT DO NOTHING：l2_reply_id = "l2r:<uuid4 12-hex>"，
                        -- 由 layer2_engine 每次呼叫新鑄（uuid4），碰撞機率 ~0（生日界
                        -- 在 2^48 空間需 ~1670 萬列才達 1e-6）。故不驗 rowcount 判
                        -- 重複——唯一現實觸發是 D3 寫入冪等 retry（同 reply_id 重放），
                        -- 此時靜默 no-op 正是要的（append-only，不覆蓋既有取證列）。
                        ON CONFLICT (l2_reply_id, created_at) DO NOTHING
                        """,
                        (
                            l2_reply_id, session_id, capability_id, trigger, created_at,
                            model, model_version, contract_ver, schema_ver,
                            sanitized_prompt,
                            _to_jsonb_str(sanitized_input_context),
                            sanitized_response,
                            _to_jsonb_str(sanitized_parsed) if sanitized_parsed is not None else None,
                            guard_verdict,
                            _to_jsonb_str(sanitized_fia) if sanitized_fia is not None else None,
                            input_tokens, output_tokens,
                            cost_usd, latency_ms, prompt_sha256, response_sha256,
                            _redactor.REDACTOR_VERSION, error_code, consequential_at_creation,
                        ),
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001 — 寫失敗 rollback + fail-soft
                    result["ok"] = False
                    result["ledger_state"] = "l2_call_ledger_write_failed"
                    result["errors"].append("insert_failed")
                    logger.warning("record_l2_call insert failed (fail-soft): %s", exc)
                    try:
                        conn.rollback()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as exc:  # noqa: BLE001 — 連線層失敗亦 fail-soft，不阻斷 session
            result["ok"] = False
            result["ledger_state"] = "l2_call_ledger_write_failed"
            result["errors"].append("conn_failed")
            logger.warning("record_l2_call conn failed (fail-soft): %s", exc)

        return result

    def record_consequential_mark(
        self,
        *,
        l2_reply_id: str,
        reason: str,
        lane: str | None = None,
        marked_by: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """落 agent.l2_consequential_marks 一列（事後「成為 consequential」事件）。

        為什麼是 INSERT 非 ledger UPDATE：同一 l2_reply_id 可被多次/多原因標記；
        event-sourced（V054 lease_transitions 範式）保持 ledger 純淨可壓縮。
        details 過 redact_jsonb 防 secret 漏入。
        """
        result: dict[str, Any] = {"ok": True, "errors": []}
        safe_details = _redactor.redact_jsonb(details or {})
        try:
            with self._conn_provider() as conn:
                if conn is None:
                    result["ok"] = False
                    result["errors"].append("db_unavailable")
                    return result
                try:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO agent.l2_consequential_marks
                            (l2_reply_id, reason, lane, marked_by, details)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (l2_reply_id, reason, lane, marked_by, _to_jsonb_str(safe_details)),
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    result["ok"] = False
                    result["errors"].append("insert_failed")
                    logger.warning("record_consequential_mark failed (fail-soft): %s", exc)
                    try:
                        conn.rollback()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["errors"].append("conn_failed")
            logger.warning("record_consequential_mark conn failed (fail-soft): %s", exc)
        return result

    def record_gate_seam(
        self,
        *,
        l2_reply_id: str,
        gate_id: str,
        verdict: str,
        applier: str | None = None,
        applied_as: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """落 learning.l2_gate_seam_log 一列（哪個 gate 以何 verdict 放行 artifact）。

        verdict 必為 pass|clamp|reject（DB CHECK 強制；本層不再二次驗，讓 DB fail-loud）。
        details 過 redact_jsonb。
        """
        result: dict[str, Any] = {"ok": True, "errors": []}
        safe_details = _redactor.redact_jsonb(details or {})
        try:
            with self._conn_provider() as conn:
                if conn is None:
                    result["ok"] = False
                    result["errors"].append("db_unavailable")
                    return result
                try:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO learning.l2_gate_seam_log
                            (l2_reply_id, gate_id, verdict, applier, applied_as, details)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (l2_reply_id, gate_id, verdict, applier, applied_as, _to_jsonb_str(safe_details)),
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    result["ok"] = False
                    result["errors"].append("insert_failed")
                    logger.warning("record_gate_seam failed (fail-soft): %s", exc)
                    try:
                        conn.rollback()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["errors"].append("conn_failed")
            logger.warning("record_gate_seam conn failed (fail-soft): %s", exc)
        return result


# ── process-global singleton（module-level binding；CLAUDE §九 已登記 SSOT）──
_WRITER: L2CallLedgerWriter | None = None


def get_l2_call_ledger_writer() -> L2CallLedgerWriter:
    """取 D3 writer singleton（首次 lazy 構造）。"""
    global _WRITER
    if _WRITER is None:
        _WRITER = L2CallLedgerWriter()
    return _WRITER


def _reset_l2_call_ledger_writer_for_tests() -> None:
    """僅供測試：清空 singleton（避免跨測試注入 conn_provider 殘留）。"""
    global _WRITER
    _WRITER = None


__all__ = [
    "L2CallLedgerWriter",
    "get_l2_call_ledger_writer",
    "_reset_l2_call_ledger_writer_for_tests",
]
