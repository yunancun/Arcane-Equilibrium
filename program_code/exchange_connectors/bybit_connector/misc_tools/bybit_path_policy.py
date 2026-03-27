#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shared path policy helper for the local BybitOpenClaw repo.

Design goal:
- provide a single place for canonical repo-local path resolution
- reduce future re-introduction of hardcoded /home/ncyu/srv paths
- keep compatibility path visible, but not the preferred target for new code
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
COMPAT_ROOT = Path("/home/ncyu/srv")

DOCKER_PROJECTS_ROOT = REPO_ROOT / "docker_projects"
PROGRAM_CODE_ROOT = REPO_ROOT / "program_code"
SETTINGS_ROOT = REPO_ROOT / "settings"
LOG_ROOT = REPO_ROOT / "log_files"
HELPER_SCRIPTS_ROOT = REPO_ROOT / "helper_scripts"

TRADING_SERVICES_ROOT = DOCKER_PROJECTS_ROOT / "trading_services"
BYBIT_RUNTIME_ROOT = TRADING_SERVICES_ROOT / "runtime" / "bybit"
THOUGHT_GATE_RUNTIME_DIR = BYBIT_RUNTIME_ROOT / "thought_gate"

# D chapter paths / D 章路径
CONNECTOR_LOGS_ROOT = TRADING_SERVICES_ROOT / "connector_logs" / "bybit"
DECISION_PACKETS_ROOT = TRADING_SERVICES_ROOT / "decision_packets" / "bybit"
VERDICTS_ROOT = TRADING_SERVICES_ROOT / "verdicts" / "bybit"
BUSINESS_EVENTS_RUNTIME_DIR = BYBIT_RUNTIME_ROOT / "business_events"
WS_LOGS_DIR = CONNECTOR_LOGS_ROOT / "ws"
WS_PERSISTENT_DIR = CONNECTOR_LOGS_ROOT / "ws_persistent"

# H0 paths / H0 章路径
LOCAL_JUDGMENT_RUNTIME_DIR = BYBIT_RUNTIME_ROOT / "local_judgment"

# I chapter paths / I 章路径
DECISION_LEASE_RUNTIME_DIR = BYBIT_RUNTIME_ROOT / "decision_lease"


def get_repo_root() -> Path:
    return REPO_ROOT


def get_compat_root() -> Path:
    return COMPAT_ROOT


def get_program_code_root() -> Path:
    return PROGRAM_CODE_ROOT


def get_settings_root() -> Path:
    return SETTINGS_ROOT


def get_log_root() -> Path:
    return LOG_ROOT


def get_helper_scripts_root() -> Path:
    return HELPER_SCRIPTS_ROOT


def get_trading_services_root() -> Path:
    return TRADING_SERVICES_ROOT


def get_bybit_runtime_root() -> Path:
    return BYBIT_RUNTIME_ROOT


def get_thought_gate_runtime_dir() -> Path:
    return THOUGHT_GATE_RUNTIME_DIR


def get_connector_logs_root() -> Path:
    return CONNECTOR_LOGS_ROOT


def get_decision_packets_root() -> Path:
    return DECISION_PACKETS_ROOT


def get_verdicts_root() -> Path:
    return VERDICTS_ROOT


def get_business_events_runtime_dir() -> Path:
    return BUSINESS_EVENTS_RUNTIME_DIR


def get_local_judgment_runtime_dir() -> Path:
    return LOCAL_JUDGMENT_RUNTIME_DIR


def get_decision_lease_runtime_dir() -> Path:
    return DECISION_LEASE_RUNTIME_DIR


def compat_root_points_to_repo_root() -> bool:
    try:
        return COMPAT_ROOT.resolve() == REPO_ROOT.resolve()
    except Exception:
        return False


__all__ = [
    "REPO_ROOT",
    "COMPAT_ROOT",
    "DOCKER_PROJECTS_ROOT",
    "PROGRAM_CODE_ROOT",
    "SETTINGS_ROOT",
    "LOG_ROOT",
    "HELPER_SCRIPTS_ROOT",
    "TRADING_SERVICES_ROOT",
    "BYBIT_RUNTIME_ROOT",
    "THOUGHT_GATE_RUNTIME_DIR",
    "CONNECTOR_LOGS_ROOT",
    "DECISION_PACKETS_ROOT",
    "VERDICTS_ROOT",
    "BUSINESS_EVENTS_RUNTIME_DIR",
    "WS_LOGS_DIR",
    "WS_PERSISTENT_DIR",
    "LOCAL_JUDGMENT_RUNTIME_DIR",
    "DECISION_LEASE_RUNTIME_DIR",
    "get_repo_root",
    "get_compat_root",
    "get_program_code_root",
    "get_settings_root",
    "get_log_root",
    "get_helper_scripts_root",
    "get_trading_services_root",
    "get_bybit_runtime_root",
    "get_thought_gate_runtime_dir",
    "get_connector_logs_root",
    "get_decision_packets_root",
    "get_verdicts_root",
    "get_business_events_runtime_dir",
    "get_local_judgment_runtime_dir",
    "get_decision_lease_runtime_dir",
    "compat_root_points_to_repo_root",
]
