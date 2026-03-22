#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Remove legacy AI env keys from env files.
  从 env 文件中删除旧版 AI 相关变量。

- purpose / 目的:
  Clean old H1E/H1F compatibility-layer variables so that only the new
  route-based config remains.
  清除旧 H1E/H1F 兼容层变量，仅保留新的 route 配置。

- behavior / 行为:
  1) Keep comments and unrelated env lines unchanged.
  2) Remove only exact legacy keys.
  3) Preserve file order for remaining lines.
"""

from pathlib import Path

TARGET_FILES = [
    Path("/home/ncyu/srv/settings/environment_files/trading_services.env"),
    Path("/home/ncyu/srv/docker_projects/trading_services/.env"),
]

LEGACY_KEYS = {
    "BYBIT_H1E_AI_PROVIDER",
    "BYBIT_H1E_LIGHT_MODEL_NAME",
    "BYBIT_H1E_STANDARD_MODEL_NAME",
    "BYBIT_H1F_PROVIDER_MODE",
    "BYBIT_H1F_API_BASE_URL",
    "BYBIT_H1F_API_KEY",

    "BYBIT_H1E_ROUTE_A_PROVIDER",
    "BYBIT_H1E_ROUTE_B_PROVIDER",
    "BYBIT_H1E_ROUTE_C_PROVIDER",

    "BYBIT_H1E_ROUTE_A_MODEL",
    "BYBIT_H1E_ROUTE_B_MODEL",
    "BYBIT_H1E_ROUTE_C_MODEL",

    "BYBIT_H1F_ROUTE_A_API_BASE_URL",
    "BYBIT_H1F_ROUTE_B_API_BASE_URL",
    "BYBIT_H1F_ROUTE_C_API_BASE_URL",

    "BYBIT_H1E_API_TIMEOUT_MS",
    "BYBIT_H1E_CONNECT_TIMEOUT_MS",
    "BYBIT_H1E_MAX_RETRIES",

    "BYBIT_H1F_API_TIMEOUT_MS",
    "BYBIT_H1F_CONNECT_TIMEOUT_MS",
    "BYBIT_H1F_MAX_RETRIES",
}

def should_drop(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    if "=" not in stripped:
        return False
    key = stripped.split("=", 1)[0].strip()
    return key in LEGACY_KEYS

def cleanup_file(path: Path) -> None:
    if not path.exists():
        print(f"[skip] not found: {path}")
        return

    original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept_lines = []
    removed = []

    for line in original_lines:
        if should_drop(line):
            removed.append(line.rstrip("\n"))
        else:
            kept_lines.append(line)

    path.write_text("".join(kept_lines), encoding="utf-8")

    print(f"[cleaned] {path}")
    print(f"  removed_count = {len(removed)}")
    for item in removed:
        print(f"  - {item}")

def main() -> None:
    for file_path in TARGET_FILES:
        cleanup_file(file_path)

if __name__ == "__main__":
    main()
