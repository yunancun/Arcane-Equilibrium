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
    "get_repo_root",
    "get_compat_root",
    "get_program_code_root",
    "get_settings_root",
    "get_log_root",
    "get_helper_scripts_root",
    "get_trading_services_root",
    "get_bybit_runtime_root",
    "get_thought_gate_runtime_dir",
    "compat_root_points_to_repo_root",
]
