#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MODULE_NOTE / 模块说明:
- 模块用途: P1-12 + P2-08(c) route binder 端到端 fixture 测试。
- 覆盖（证明 should_call_ai=true 的路由真正到达 provider 绑定或诚实阻断）:
  * standard lane → route_b_standard → 绑定 ROUTE_B provider，非空 provider_target。
  * route C → route_c_escalated_standard → 绑定 ROUTE_C（canonical enum 被接受，不掉 skip）。
  * route A 默认无 paid opt-in → 绑定 LOCAL/FREE（ollama_local），无付费支出（P2-08c）。
  * route A + BYBIT_ROUTE_A_PAID_OPT_IN=1 → 才绑定配置的付费 provider。
  * route_skip → provider_target 为空（诚实阻断，不假装可调用）。
- 依赖: 在临时 _SRV 目录布出 route selector JSON，OPENCLAW_SRV_ROOT 指向它后跑 binder。
  binder 是 shell 脚本，subprocess 调用并解析 emit 出的 export 行。不连真实 provider。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

_BINDER = (
    Path(__file__).resolve().parents[3]
    / "exchange_connectors/bybit_connector/misc_tools/bybit_bind_active_route_env.sh"
)
_ROUTE_REL = "docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_route_selector_latest.json"
# binder 的内嵌 Python 只从这些 env 文件读取 provider 配置（不读 OS env）。
_ENV_REL = "docker_projects/trading_services/.env"


def _write_env(srv_root: Path, kv: dict) -> None:
    env_path = srv_root / _ENV_REL
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in kv.items()) + "\n", encoding="utf-8"
    )


def _write_route(srv_root: Path, route_plan: str, group: str, tier: str) -> None:
    route_path = srv_root / _ROUTE_REL
    route_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "route_decision": {
            "route_plan": route_plan,
            "route_reason": "test_fixture",
            "selected_ai_tier": tier,
            "env_binding_group": group,
        }
    }
    route_path.write_text(json.dumps(payload), encoding="utf-8")


def _run_binder(srv_root: Path, extra_env: dict | None = None) -> dict:
    env = dict(os.environ)
    env["OPENCLAW_SRV_ROOT"] = str(srv_root)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["bash", str(_BINDER)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, f"binder failed: {proc.stderr}"
    out = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("export "):
            kv = line[len("export "):]
            if "=" in kv:
                k, v = kv.split("=", 1)
                out[k] = v.strip("'")
    return out


@pytest.fixture()
def srv_root(tmp_path):
    return tmp_path


def test_standard_lane_binds_route_b_provider(srv_root):
    _write_route(srv_root, "route_b_standard", "ROUTE_B", "standard")
    out = _run_binder(srv_root)
    assert out["BYBIT_AI_ACTIVE_ROUTE_TIER"] == "standard"
    # should_call_ai=true 的 standard 路由必须到达非空 provider 绑定。
    assert out["BYBIT_AI_ACTIVE_PROVIDER_TARGET"] == "openai_native"


def test_route_c_canonical_enum_binds_route_c(srv_root):
    # P1-12：canonical route_c_escalated_standard 必须被接受，不掉进 skip 分支。
    _write_route(srv_root, "route_c_escalated_standard", "ROUTE_C", "standard")
    out = _run_binder(srv_root)
    assert out["BYBIT_AI_ACTIVE_ROUTE_TIER"] != "skip"
    assert out["BYBIT_AI_ACTIVE_PROVIDER_TARGET"] != ""


def test_route_a_default_binds_local_free(srv_root):
    # P2-08(c)：route A 默认 LOCAL/FREE，不产生付费支出。
    _write_route(srv_root, "route_a_light", "ROUTE_A", "light")
    out = _run_binder(srv_root)
    assert out["BYBIT_AI_ACTIVE_PROVIDER_TARGET"] == "ollama_local"


def test_route_a_paid_opt_in_binds_paid(srv_root):
    _write_route(srv_root, "route_a_light", "ROUTE_A", "light")
    # opt-in 与 provider 配置经 env 文件提供（binder 只从 env 文件读 provider 配置）。
    _write_env(srv_root, {
        "BYBIT_ROUTE_A_PAID_OPT_IN": "1",
        "BYBIT_ROUTE_A_PROVIDER_TARGET": "anthropic_native",
    })
    out = _run_binder(srv_root)
    assert out["BYBIT_AI_ACTIVE_PROVIDER_TARGET"] == "anthropic_native"


def test_route_skip_blocks_honestly_empty_provider(srv_root):
    # 负向：route_skip 不假装可调用——provider 为空。
    _write_route(srv_root, "route_skip", "ROUTE_SKIP", "skip")
    out = _run_binder(srv_root)
    assert out["BYBIT_AI_ACTIVE_ROUTE_TIER"] == "skip"
    assert out["BYBIT_AI_ACTIVE_PROVIDER_TARGET"] == ""
