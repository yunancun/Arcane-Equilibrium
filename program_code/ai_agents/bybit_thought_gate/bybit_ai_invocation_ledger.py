#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODULE_NOTE / 模块说明:
- 模块用途:
  P1-13 持久化账本写入器。H1-F provider-native AI 调用 resolve 之后，把单次
  调用同时落库到两张已部署的账本表：
    1) agent.ai_invocations    —— 单次调用 lineage/审计（对齐 V003+V015 schema）
    2) learning.ai_usage_log   —— 预算 MTD 计量（Rust BudgetTracker 读取的权威账本）
- 主要函数: resolve_dsn / write_invocation_ledger
- 依赖: psycopg（缺失时本地路径降级、付费路径 fail-closed）；DSN 解析与
  program_code/ml_training/model_registry._connect 对齐，全 ml/ai 模块共用 env 顺序。
- 硬边界:
  * 付费 provider-native 调用（openai_native / anthropic_native）账本写失败 →
    返回 ok=False，调用方必须 fail-closed（视为未记录，不允许进度 / 不满足 cost gate）。
    为什么 fail-closed：付费调用已在 provider 端真实发生且产生成本，本地未落库即
    无法核算预算，绝不能让其绕过 cost cap。
  * 本地/免费路径（ollama_local / 无 provider / no_call_path_accepted）→ best-effort，
    写失败只警告（根原则 14：基线无需付费服务即可运行）。
  * 本模块不发起任何 provider HTTP；只做 DB 落库。不复制 provider SDK 逻辑。

注：H1-F 是 ai_agents 独立 CLI 脚本，无法 import control_api_v1 app 包内的
record_ai_invocation；故此处用相同 SQL 契约（与 agent_event_store.record_ai_invocation
对齐）实现一个独立的轻量写入器，而非新建表或新建写语义。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("bybit_ai_invocation_ledger")

# 付费 provider 集合：仅这两类触发 fail-closed 账本契约。
PAID_PROVIDERS = {"openai_native", "anthropic_native"}

# 调用视为成功的 invocation_state 集合（用于 success 列）。
_SUCCESS_STATES = {
    "invocation_success_json_ready",
    "invocation_success_text_only",
}


def _sha256_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def deterministic_event_ts(idempotency_key: str, *, _now: Optional[datetime] = None) -> datetime:
    """由 idempotency_key 推导一个稳定的 UTC timestamptz，作为两张账本表 PK 的时间分量。

    为什么必须确定性（MED-1 cost-correctness 修复）：
      两表 PK 含时间列——agent.ai_invocations(invocation_id, ts) 与
      learning.ai_usage_log(time, scope, request_id)。若时间列取 now()，同一笔 H1-F
      调用在重试时会拿到不同的 ts/time，PK 不相同，ON CONFLICT DO NOTHING 永不命中，
      于是重试写入第二行 → 在 MTD 权威预算账本里重复计费（double-count spend）。
      把时间分量绑定到 idempotency_key 后，重试得到完全相同的 PK，去重才真正生效。

    必须保住 MTD 正确性：learning.ai_usage_log.time 是 BudgetTracker 做月度求和的依据，
    时间分量不能落到错误月份。因此优先解析 idempotency_key 内嵌的真实毫秒事件时间
    （H1-F 默认 key 形如 "h1f_<now_ms>"），用调用当时捕获、重试不变的逻辑事件时间作为 ts。

    无内嵌时间的外部 key：退而求其次，把 SHA256(key) 映射成「当月内」的确定性秒偏移。
    同月重试得到同一 PK（去重生效）；跨月边界的极端重试最坏情况是少量重复行，但仍
    保证落在 ±1 个月内、不会错配到任意历史月份。秒级粒度对 MTD 求和足够。
    """
    # 1) 优先：从 key 内嵌的毫秒时间还原真实事件时间（与捕获时刻一致，重试不变）。
    embedded_ms = _extract_embedded_ms(idempotency_key)
    if embedded_ms is not None:
        return datetime.fromtimestamp(embedded_ms / 1000.0, tz=timezone.utc)

    # 2) 退化：锚定到「当月」，保 MTD 不错月；月内偏移由 key hash 确定。
    now = _now or datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).digest()
    # 当月秒数上界（28 天足以覆盖任意月份且不越界到下月）。
    offset_seconds = int.from_bytes(digest[:8], "big") % (28 * 24 * 3600)
    return datetime.fromtimestamp(month_start.timestamp() + offset_seconds, tz=timezone.utc)


def _extract_embedded_ms(idempotency_key: str) -> Optional[int]:
    """从形如 "h1f_<ms>" 或末段为纯数字毫秒的 key 中解析内嵌事件毫秒；解析失败返回 None。"""
    if not idempotency_key:
        return None
    tail = idempotency_key.rsplit("_", 1)[-1]
    if tail.isdigit() and len(tail) >= 12:  # 13 位左右才像毫秒纪元，避免误吞短数字。
        try:
            return int(tail)
        except ValueError:
            return None
    return None


def resolve_dsn(dsn: Optional[str] = None) -> Optional[str]:
    """解析 PG DSN，顺序与 model_registry._connect 完全一致。

    OPENCLAW_DATABASE_URL → DSN → POSTGRES_*；全不可得返回 None。
    """
    conninfo = dsn or os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DSN")
    if conninfo:
        return conninfo
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    db = os.environ.get("POSTGRES_DB")
    if user and db:
        host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
        port = os.environ.get("POSTGRES_PORT", "5432")
        return f"postgresql://{user}:{password or ''}@{host}:{port}/{db}"
    return None


def _connect(dsn: Optional[str] = None):
    """开短生命周期 psycopg 连线；psycopg 缺失 / DSN 缺失 / 连线失败 → None。"""
    try:
        import psycopg  # noqa: F401
    except ImportError:
        logger.info("ai_invocation_ledger: psycopg not installed; skipping DB write")
        return None
    conninfo = resolve_dsn(dsn)
    if not conninfo:
        logger.info(
            "ai_invocation_ledger: no DSN (OPENCLAW_DATABASE_URL / DSN / POSTGRES_* unset); skipping"
        )
        return None
    try:
        import psycopg
        return psycopg.connect(conninfo)
    except Exception as e:  # noqa: BLE001
        logger.warning("ai_invocation_ledger: connect failed: %s", e)
        return None


def write_invocation_ledger(
    *,
    idempotency_key: str,
    provider_target: str,
    model_name: str,
    selected_ai_tier: Optional[str],
    route_plan: Optional[str],
    invocation_state: str,
    usage_summary: Optional[Dict[str, Any]],
    cost_usd: Optional[float],
    latency_ms: Optional[int],
    prompt_material: Optional[str] = None,
    response_material: Optional[str] = None,
    engine_mode: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    budget_scope: str = "thought_gate",
    dsn: Optional[str] = None,
    _conn_factory=None,
) -> Dict[str, Any]:
    """把单次 H1-F 调用写入两张账本表，按 idempotency_key 去重。

    返回 dict:
      ok               -- bool，两张表是否都成功落库（或合法跳过）
      ledger_state     -- 文字状态供 H1-F payload 记录
      paid             -- bool，是否付费 provider
      rows_written     -- list[str]，实际写入的表名
      errors           -- list[str]
    付费调用任一表写失败 → ok=False（caller 必 fail-closed）；本地路径写失败 ok=True
    但带 warning（best-effort）。_conn_factory 仅供测试注入。

    幂等（MED-1 修复后）：两张表 PK 都含时间列——agent.ai_invocations(invocation_id, ts)、
    learning.ai_usage_log(time, scope, request_id)。时间分量由 deterministic_event_ts
    从 idempotency_key 确定性推导（不再用 now()），故重试拿到完全相同的 PK，
    ON CONFLICT DO NOTHING 真正命中，重试只保留一行，不会在 MTD 预算账本重复计费。
    """
    paid = provider_target in PAID_PROVIDERS
    usage = usage_summary or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    success = invocation_state in _SUCCESS_STATES
    detail_payload: Dict[str, Any] = dict(details or {})
    detail_payload.setdefault("route_plan", route_plan)
    detail_payload.setdefault("invocation_state", invocation_state)

    result: Dict[str, Any] = {
        "ok": True,
        "ledger_state": "ai_invocation_ledger_recorded",
        "paid": paid,
        "rows_written": [],
        "errors": [],
    }

    connect = _conn_factory or _connect
    conn = connect(dsn)
    if conn is None:
        # 无法连库：付费 fail-closed，本地 best-effort。
        if paid:
            result["ok"] = False
            result["ledger_state"] = "invocation_ledger_write_failed"
            result["errors"].append("db_unavailable_for_paid_call")
        else:
            result["ledger_state"] = "ai_invocation_ledger_skipped_local_best_effort"
            result["errors"].append("db_unavailable_local_best_effort")
        return result

    prompt_hash = _sha256_text(prompt_material)
    cost_value = float(cost_usd) if cost_usd is not None else 0.0
    purpose = route_plan or "h1f_thought_gate"
    # MED-1：时间分量必须由 idempotency_key 确定性推导，重试得到同一 PK，去重才生效。
    event_ts = deterministic_event_ts(idempotency_key)
    # ai_usage_log.provider 用归一化短名（local_ollama / openai / anthropic）。
    usage_provider = {
        "openai_native": "openai",
        "anthropic_native": "anthropic",
        "ollama_local": "local_ollama",
    }.get(provider_target, provider_target or "unknown")

    try:
        with conn:
            with conn.cursor() as cur:
                # 1) agent.ai_invocations —— 单次 lineage（对齐 record_ai_invocation 列）
                cur.execute(
                    """
                    INSERT INTO agent.ai_invocations (
                        ts, invocation_id, provider, model, tier, purpose,
                        prompt_hash, input_tokens, output_tokens, cost_usd,
                        latency_ms, success, response_summary, context_id,
                        details, engine_mode
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s
                    )
                    ON CONFLICT (invocation_id, ts) DO NOTHING
                    """,
                    (
                        event_ts,
                        idempotency_key,
                        provider_target or "unknown",
                        model_name or "unknown",
                        selected_ai_tier,
                        purpose,
                        prompt_hash,
                        input_tokens,
                        output_tokens,
                        cost_value,
                        int(latency_ms or 0),
                        bool(success),
                        _sha256_text(response_material),
                        idempotency_key,
                        json.dumps(detail_payload, ensure_ascii=False),
                        engine_mode,
                    ),
                )
                result["rows_written"].append("agent.ai_invocations")

                # 2) learning.ai_usage_log —— 预算 MTD 计量（Rust BudgetTracker 读取）
                cur.execute(
                    """
                    INSERT INTO learning.ai_usage_log (
                        time, scope, provider, model,
                        tokens_in, tokens_out, cost_usd, purpose, request_id
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (time, scope, request_id) DO NOTHING
                    """,
                    (
                        event_ts,
                        budget_scope,
                        usage_provider,
                        model_name or "unknown",
                        input_tokens,
                        output_tokens,
                        cost_value,
                        purpose,
                        idempotency_key,
                    ),
                )
                result["rows_written"].append("learning.ai_usage_log")
    except Exception as e:  # noqa: BLE001
        msg = f"ledger_write_exception:{e.__class__.__name__}"
        if paid:
            result["ok"] = False
            result["ledger_state"] = "invocation_ledger_write_failed"
            result["errors"].append(msg)
            logger.error("ai_invocation_ledger: PAID call ledger write failed: %s", e)
        else:
            result["ledger_state"] = "ai_invocation_ledger_skipped_local_best_effort"
            result["errors"].append(msg)
            logger.warning("ai_invocation_ledger: local call ledger write failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    return result
