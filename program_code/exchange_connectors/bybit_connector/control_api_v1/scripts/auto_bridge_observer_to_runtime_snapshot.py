#!/usr/bin/env python3
from __future__ import annotations

"""
Observer → Runtime Snapshot 自动桥接脚本
Auto-bridge: reads observer pipeline outputs and generates a runtime snapshot
for the Control API to consume via OPENCLAW_RUNTIME_SNAPSHOT_FILE.

MODULE_NOTE (中文):
  本脚本是 observer pipeline 与 Control API 之间的自动桥接器。
  它读取 observer 的三个输出文件：
    1. bybit_system_snapshot_latest.json  — 账户/持仓/订单/成交 REST 数据
    2. bybit_ws_runtime_facts_latest.json — WebSocket 连接健康状态
    3. bybit_observer_verdict_latest.json — 综合判决（freshness、risk flags、执行许可）

  从这些数据中提取关键事实，生成符合 runtime_snapshot_contract 的标准快照文件，
  写入 OPENCLAW_RUNTIME_SNAPSHOT_FILE 指定路径，供 Control API 的 runtime_bridge 实时读取。

  支持两种运行模式：
    1. 单次模式（默认）：读取 → 生成 → 写入 → 退出
    2. 循环模式（--loop）：每 N 秒重复执行，保持快照持续更新

MODULE_NOTE (English):
  This script is the auto-bridge between the observer pipeline and the Control API.
  It reads three observer output files:
    1. bybit_system_snapshot_latest.json  — Account/position/order/execution REST data
    2. bybit_ws_runtime_facts_latest.json — WebSocket connection health
    3. bybit_observer_verdict_latest.json — Combined verdict (freshness, risk flags, execution permission)

  Extracts key facts, generates a runtime snapshot conforming to runtime_snapshot_contract,
  writes to the path specified by OPENCLAW_RUNTIME_SNAPSHOT_FILE for the Control API's
  runtime_bridge to read in real-time.

  Two run modes:
    1. One-shot (default): read → generate → write → exit
    2. Loop (--loop): repeat every N seconds for continuous snapshot refresh

安全不变量 / Safety invariant:
  - 仅读取 observer 输出文件 + 写入 runtime snapshot，绝不调用 Bybit API
  - Only reads observer output files + writes runtime snapshot, never calls Bybit API
  - system_mode / execution_state / execution_authority 全程不变
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Default File Paths / 默认文件路径
# ═══════════════════════════════════════════════════════════════════════════════

# Observer output directory (standard location)
# Observer 输出目录（标准位置）
TRADING_SERVICES_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services")

DEFAULT_SYSTEM_SNAPSHOT_PATH = TRADING_SERVICES_DIR / "connector_logs/bybit/bybit_system_snapshot_latest.json"
DEFAULT_WS_FACTS_PATH = TRADING_SERVICES_DIR / "runtime/bybit/bybit_ws_runtime_facts_latest.json"
DEFAULT_VERDICT_PATH = TRADING_SERVICES_DIR / "verdicts/bybit/bybit_observer_verdict_latest.json"

# Default output path for generated runtime snapshot
# 生成的 runtime snapshot 默认输出路径
DEFAULT_OUTPUT_PATH = TRADING_SERVICES_DIR / "runtime/bybit/runtime_snapshot_generated.json"

# Staleness threshold: if source data is older than this, mark as stale
# 过期阈值：源数据超过此时间则标记为 stale
STALENESS_THRESHOLD_MS = 120_000  # 2 minutes / 2 分钟


# ═══════════════════════════════════════════════════════════════════════════════
# File I/O / 文件读写
# ═══════════════════════════════════════════════════════════════════════════════

def load_json(path: Path) -> dict[str, Any] | None:
    """Load JSON file, return None if missing or invalid / 加载 JSON 文件"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] Failed to load {path}: {e}", file=sys.stderr)
        return None


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    """Write runtime snapshot with safe permissions / 写入 runtime snapshot"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(str(path), 0o600)


# ═══════════════════════════════════════════════════════════════════════════════
# Core: Extract Facts from Observer Outputs / 从 Observer 输出中提取事实
# ═══════════════════════════════════════════════════════════════════════════════

def extract_connection_states(
    system_snapshot: dict[str, Any] | None,
    ws_facts: dict[str, Any] | None,
) -> dict[str, str]:
    """
    Derive REST and WS connection states from observer data.
    从 observer 数据推导 REST 和 WS 连接状态。
    """
    # REST connection state: based on system snapshot sources
    # REST 连接状态：基于系统快照的源数据
    rest_state = "unknown"
    if system_snapshot:
        sources = system_snapshot.get("sources", {})
        all_ok = all(
            s.get("ok", False)
            for s in sources.values()
            if isinstance(s, dict)
        )
        rest_state = "ready" if all_ok else "degraded"

    # WS connection state: based on ws_runtime_facts
    # WS 连接状态：基于 WS 运行时事实
    ws_state = "unknown"
    if ws_facts:
        conn_state = ws_facts.get("connection_state", "unknown")
        if conn_state == "connected":
            ws_state = "ready"
        elif conn_state in ("disconnected", "reconnecting"):
            ws_state = "degraded"
        else:
            ws_state = "unknown"

    return {
        "rest_private_connection_state": rest_state,
        "ws_private_connection_state": ws_state,
    }


def extract_freshness_state(
    verdict: dict[str, Any] | None,
    now_ms: int,
) -> str:
    """
    Determine data freshness from verdict timestamps.
    从判决时间戳确定数据新鲜度。
    """
    if not verdict:
        return "unknown"

    verdict_ts = verdict.get("verdict_generated_ts_ms", 0)
    if verdict_ts <= 0:
        return "unknown"

    age_ms = now_ms - verdict_ts
    if age_ms < STALENESS_THRESHOLD_MS:
        return "fresh"
    else:
        return "stale"


def extract_completeness(
    system_snapshot: dict[str, Any] | None,
) -> dict[str, str]:
    """
    Determine account and source snapshot completeness.
    确定账户和源快照的完整性。
    """
    if not system_snapshot:
        return {
            "account_fact_completeness_state": "missing",
            "source_snapshot_completeness_state": "missing",
        }

    sources = system_snapshot.get("sources", {})
    account_ok = sources.get("account", {}).get("ok", False)
    positions_ok = sources.get("positions", {}).get("ok", False)

    all_sources_ok = all(
        s.get("ok", False)
        for s in sources.values()
        if isinstance(s, dict)
    )

    return {
        "account_fact_completeness_state": "complete" if account_ok else "partial",
        "source_snapshot_completeness_state": "complete" if all_sources_ok else "partial",
    }


def extract_product_family_facts(
    system_snapshot: dict[str, Any] | None,
) -> dict[str, dict[str, str]]:
    """
    Derive product family permission facts from observer data.
    从 observer 数据推导产品族权限事实。

    In read_only mode with a UNIFIED account, all families that Bybit supports
    are readonly_visible. We mark options and other_derivatives as unavailable
    since we haven't validated observer support for them yet.
    """
    # Default: all families have the permissions we can verify from observer
    # 默认：所有产品族具有我们能从 observer 验证的权限
    base_fact = {
        "exchange_permission_fact": "readonly_visible",
        "account_permission_fact": "readonly_visible",
    }
    unavailable = {
        "exchange_permission_fact": "unavailable",
        "account_permission_fact": "unavailable",
    }

    families = {}

    if system_snapshot:
        account_type = _extract_account_type(system_snapshot)
        has_account = account_type is not None

        # Spot, margin, perp_linear: verified from observer REST calls
        families["spot"] = dict(base_fact) if has_account else dict(unavailable)
        families["margin"] = dict(base_fact) if has_account else dict(unavailable)
        families["perp_linear"] = dict(base_fact) if has_account else dict(unavailable)
        families["perp_inverse"] = dict(base_fact) if has_account else dict(unavailable)
        # Options and other derivatives: not yet validated by observer
        families["options"] = dict(unavailable)
        families["other_derivatives_reserved"] = dict(unavailable)
    else:
        for fam in ("spot", "margin", "perp_linear", "perp_inverse", "options", "other_derivatives_reserved"):
            families[fam] = dict(unavailable)

    return families


def extract_health_telemetry(
    system_snapshot: dict[str, Any] | None,
    ws_facts: dict[str, Any] | None,
    verdict: dict[str, Any] | None,
    now_ms: int,
) -> dict[str, Any]:
    """
    Build health telemetry section from observer data.
    从 observer 数据构建健康遥测部分。
    """
    # Compute health scores / 计算健康分数
    exchange_score = 100
    infra_score = 100
    data_freshness_score = 100

    # Deduct for REST issues / REST 问题扣分
    if system_snapshot:
        sources = system_snapshot.get("sources", {})
        for s in sources.values():
            if isinstance(s, dict) and not s.get("ok", False):
                exchange_score -= 25

    # Deduct for WS issues / WS 问题扣分
    ws_disconnect_count = 0
    if ws_facts:
        health = ws_facts.get("listener_health", "unknown")
        if health in ("disconnected", "error"):
            infra_score -= 50
        conn_state = ws_facts.get("connection_state", "unknown")
        if conn_state != "connected":
            ws_disconnect_count = 1

    # Freshness score / 新鲜度分数
    if verdict:
        freshness = verdict.get("freshness", {})
        snapshot_age = freshness.get("snapshot_age_ms", 0)
        if snapshot_age > STALENESS_THRESHOLD_MS:
            data_freshness_score -= 50
        elif snapshot_age > STALENESS_THRESHOLD_MS / 2:
            data_freshness_score -= 20

    # Exchange timeout estimation / 交易所超时估算
    exchange_timeout_count = 0
    avg_latency = 0
    if system_snapshot:
        payload = system_snapshot.get("payload", {})
        latencies = []
        for stage_data in payload.values():
            if isinstance(stage_data, dict) and "latency_ms" in stage_data:
                latencies.append(stage_data["latency_ms"])
                if stage_data["latency_ms"] > 5000:
                    exchange_timeout_count += 1
        if latencies:
            avg_latency = sum(latencies) / len(latencies)

    overall = min(exchange_score, infra_score, data_freshness_score)

    # Determine gate states / 确定门控状态
    freshness_gate = "passed" if data_freshness_score >= 50 else "failed"
    exchange_gate = "passed" if exchange_timeout_count == 0 else "failed"
    ws_gate = "passed" if ws_disconnect_count == 0 else "failed"
    latency_gate = "passed" if avg_latency < 3000 else "failed"
    overall_gate = "passed" if all(
        g == "passed" for g in [freshness_gate, exchange_gate, ws_gate, latency_gate]
    ) else "failed"

    return {
        "scores": {
            "overall_health_score": max(0, overall),
            "ai_health_score": 100,  # No AI calls yet / 尚无 AI 调用
            "exchange_health_score": max(0, exchange_score),
            "infra_health_score": max(0, infra_score),
            "data_freshness_score": max(0, data_freshness_score),
        },
        "metrics": {
            "avg_ai_latency_ms": 0,
            "exchange_timeout_count": exchange_timeout_count,
            "ws_disconnect_count": ws_disconnect_count,
            "runtime_stale_count": 1 if data_freshness_score < 50 else 0,
        },
        "evaluation_context": {
            "evaluation_window_sec": 300,
            "sample_count": 1,
            "last_evaluated_ts_ms": now_ms,
            "threshold_basis": "rolling_window",
        },
        "gates": {
            "health_gates_overall_state": overall_gate,
            "exchange_timeout_gate_state": exchange_gate,
            "ws_disconnect_gate_state": ws_gate,
            "latency_gate_state": latency_gate,
            "freshness_gate_state": freshness_gate,
        },
    }


def _extract_account_type(system_snapshot: dict[str, Any]) -> str | None:
    """Extract account type from system snapshot / 从系统快照提取账户类型"""
    try:
        account_list = (
            system_snapshot
            .get("payload", {})
            .get("account", {})
            .get("response", {})
            .get("result", {})
            .get("list", [])
        )
        if account_list and isinstance(account_list[0], dict):
            return account_list[0].get("accountType")
    except (KeyError, IndexError, TypeError):
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Core: Build Runtime Snapshot / 构建 Runtime Snapshot
# ═══════════════════════════════════════════════════════════════════════════════

def build_runtime_snapshot_from_observer(
    system_snapshot: dict[str, Any] | None,
    ws_facts: dict[str, Any] | None,
    verdict: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build a complete runtime snapshot from observer pipeline outputs.
    从 observer 管线输出构建完整的 runtime snapshot。

    The generated snapshot conforms to runtime_snapshot_contract and can be
    consumed by runtime_bridge.py via OPENCLAW_RUNTIME_SNAPSHOT_FILE.
    """
    now_ms = int(time.time() * 1000)

    # 1. Connection states / 连接状态
    conn_states = extract_connection_states(system_snapshot, ws_facts)

    # 2. Overall runtime connection state / 综合运行时连接状态
    if conn_states["rest_private_connection_state"] == "ready" and conn_states["ws_private_connection_state"] == "ready":
        runtime_connection = "healthy"
    elif "degraded" in (conn_states["rest_private_connection_state"], conn_states["ws_private_connection_state"]):
        runtime_connection = "degraded"
    elif "unknown" in (conn_states["rest_private_connection_state"], conn_states["ws_private_connection_state"]):
        runtime_connection = "unknown"
    else:
        runtime_connection = "down"

    # 3. Completeness / 完整性
    completeness = extract_completeness(system_snapshot)

    # 4. Freshness / 新鲜度
    freshness_state = extract_freshness_state(verdict, now_ms)

    # 5. Product family facts / 产品族事实
    product_families = extract_product_family_facts(system_snapshot)

    # 6. Health telemetry / 健康遥测
    health = extract_health_telemetry(system_snapshot, ws_facts, verdict, now_ms)

    # 7. Determine source timestamp for the snapshot
    # 确定快照的源时间戳
    source_ts = now_ms
    if verdict:
        source_ts = verdict.get("verdict_generated_ts_ms", now_ms)
    elif system_snapshot:
        source_ts = system_snapshot.get("ts_ms", now_ms)

    # Build the snapshot / 构建快照
    snapshot: dict[str, Any] = {
        # Required top-level fields / 必需顶层字段
        "runtime_snapshot_id": f"runtime:auto-bridge:{now_ms}",
        "runtime_snapshot_ts_ms": now_ms,
        "readonly_connector_name": "bybit_prod_readonly_main",
        "execution_connector_name": None,

        # Connection states / 连接状态
        "rest_private_connection_state": conn_states["rest_private_connection_state"],
        "ws_private_connection_state": conn_states["ws_private_connection_state"],
        "runtime_connection_state": runtime_connection,

        # Completeness / 完整性
        "account_fact_completeness_state": completeness["account_fact_completeness_state"],
        "source_snapshot_completeness_state": completeness["source_snapshot_completeness_state"],

        # Global runtime facts / 全局运行时事实
        "global_runtime_facts": {
            "system_mode_fact": "shadow_only",
            "execution_state_fact": "execution_disabled",
            "runtime_last_refresh_ts_ms": source_ts,
            "runtime_data_freshness_state": freshness_state,
        },

        # Product family facts / 产品族事实
        "product_family_facts": product_families,

        # Health telemetry / 健康遥测
        "health_telemetry": health,

        # Bridge metadata / 桥接元数据
        "_bridge_meta": {
            "bridge_version": "v1",
            "bridge_ts_ms": now_ms,
            "source_system_snapshot_ts_ms": system_snapshot.get("ts_ms") if system_snapshot else None,
            "source_ws_facts_ts_ms": ws_facts.get("ts_ms") if ws_facts else None,
            "source_verdict_ts_ms": verdict.get("verdict_generated_ts_ms") if verdict else None,
            "source_verdict_code": verdict.get("verdict_code") if verdict else None,
        },
    }

    return snapshot


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / 命令行接口
# ═══════════════════════════════════════════════════════════════════════════════

def run_once(args: argparse.Namespace) -> dict[str, Any]:
    """Execute one bridge cycle / 执行一次桥接循环"""
    system_snapshot = load_json(Path(args.system_snapshot))
    ws_facts = load_json(Path(args.ws_facts))
    verdict = load_json(Path(args.verdict))

    sources_loaded = []
    if system_snapshot:
        sources_loaded.append("system_snapshot")
    if ws_facts:
        sources_loaded.append("ws_facts")
    if verdict:
        sources_loaded.append("verdict")

    if not sources_loaded:
        print("[ERROR] No observer output files found. Run observer cycle first.", file=sys.stderr)
        return {"ok": False, "error": "no_sources"}

    snapshot = build_runtime_snapshot_from_observer(system_snapshot, ws_facts, verdict)

    output_path = Path(args.output)
    write_snapshot(output_path, snapshot)

    result = {
        "ok": True,
        "output_path": str(output_path),
        "sources_loaded": sources_loaded,
        "runtime_connection_state": snapshot["runtime_connection_state"],
        "freshness_state": snapshot["global_runtime_facts"]["runtime_data_freshness_state"],
        "health_overall": snapshot["health_telemetry"]["scores"]["overall_health_score"],
        "ts_ms": snapshot["runtime_snapshot_ts_ms"],
    }

    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Auto-bridge: Observer → Runtime Snapshot / 自动桥接：Observer → Runtime Snapshot",
    )
    parser.add_argument(
        "--system-snapshot",
        default=str(DEFAULT_SYSTEM_SNAPSHOT_PATH),
        help="Path to bybit_system_snapshot_latest.json",
    )
    parser.add_argument(
        "--ws-facts",
        default=str(DEFAULT_WS_FACTS_PATH),
        help="Path to bybit_ws_runtime_facts_latest.json",
    )
    parser.add_argument(
        "--verdict",
        default=str(DEFAULT_VERDICT_PATH),
        help="Path to bybit_observer_verdict_latest.json",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Output path for generated runtime snapshot",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously, regenerating snapshot every --interval seconds",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Refresh interval in seconds (only with --loop, default: 30)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress output (only print errors)",
    )

    args = parser.parse_args()

    if args.loop:
        stop = False

        def sig_handler(signum, frame):
            nonlocal stop
            stop = True

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        print(f"[auto-bridge] Loop mode: interval={args.interval}s, output={args.output}", file=sys.stderr)
        cycle = 0
        while not stop:
            cycle += 1
            try:
                result = run_once(args)
                if not args.quiet:
                    print(f"[auto-bridge] cycle={cycle} ok={result.get('ok')} health={result.get('health_overall')}", file=sys.stderr)
            except Exception as e:
                print(f"[auto-bridge] cycle={cycle} error: {e}", file=sys.stderr)

            # Wait for next cycle, but check stop flag
            for _ in range(args.interval):
                if stop:
                    break
                time.sleep(1)

        print("[auto-bridge] Stopped.", file=sys.stderr)
    else:
        result = run_once(args)
        sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
