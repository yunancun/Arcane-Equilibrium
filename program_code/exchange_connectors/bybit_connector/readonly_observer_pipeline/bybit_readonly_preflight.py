#!/usr/bin/env python3
import json
from pathlib import Path
import os

CONFIG_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/settings/service_configs/bybit_connector_config.json")

def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""

def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    api_key_path = Path(config["credential_paths"]["api_key_file"])
    api_secret_path = Path(config["credential_paths"]["api_secret_file"])

    api_key_exists = api_key_path.exists()
    api_secret_exists = api_secret_path.exists()

    mode = config.get("mode", "unknown")
    write_enabled = bool(config.get("write_enabled", True))
    contract_version = config.get("contract_version", "unknown")

    health_state = "healthy"
    issues = []

    if mode != "read_only":
        health_state = "mode_mismatch"
        issues.append("mode is not read_only")

    if write_enabled:
        health_state = "mode_mismatch"
        issues.append("write_enabled must be false")

    if not api_key_exists or not api_secret_exists:
        health_state = "credential_misconfigured"
        issues.append("credential files missing")

    # We intentionally do NOT print secrets
    output = {
        "connector_name": config.get("connector_name"),
        "exchange_name": config.get("exchange_name"),
        "environment": config.get("environment"),
        "mode": mode,
        "contract_version": contract_version,
        "write_enabled": write_enabled,
        "api_key_file_exists": api_key_exists,
        "api_secret_file_exists": api_secret_exists,
        "health_state": health_state,
        "issues": issues,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
