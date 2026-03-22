#!/usr/bin/env python3
import json
from pathlib import Path

CONFIG_PATH = Path("/home/ncyu/srv/settings/service_configs/bybit_connector_config.json")
CONTRACT_DOC = Path("/home/ncyu/srv/settings/system_notes/bybit_private_readonly_contract_v1.md")

def main() -> None:
    issues = []

    if not CONFIG_PATH.exists():
        print(json.dumps({
            "ok": False,
            "stage": "private_readonly_precheck",
            "issues": ["missing_config_file"]
        }, ensure_ascii=False, indent=2))
        return

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    mode = config.get("mode")
    write_enabled = config.get("write_enabled")
    contract_version = config.get("contract_version")

    api_key_file = Path(config.get("credential_paths", {}).get("api_key_file", ""))
    api_secret_file = Path(config.get("credential_paths", {}).get("api_secret_file", ""))

    if mode != "read_only":
        issues.append("mode_is_not_read_only")

    if write_enabled is not False:
        issues.append("write_enabled_is_not_false")

    if not api_key_file.exists():
        issues.append("api_key_file_missing")

    if not api_secret_file.exists():
        issues.append("api_secret_file_missing")

    if not CONTRACT_DOC.exists():
        issues.append("private_readonly_contract_doc_missing")

    result = {
        "ok": len(issues) == 0,
        "stage": "private_readonly_precheck",
        "exchange_name": "bybit",
        "mode": mode,
        "write_enabled": write_enabled,
        "contract_version": contract_version,
        "api_key_file_exists": api_key_file.exists(),
        "api_secret_file_exists": api_secret_file.exists(),
        "private_contract_doc_exists": CONTRACT_DOC.exists(),
        "issues": issues
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
