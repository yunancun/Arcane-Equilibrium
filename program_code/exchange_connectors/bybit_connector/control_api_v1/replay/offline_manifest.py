"""R8 本機設定組裝器；沿用既有組裝、canonical 與簽名契約。"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from . import full_chain_fixture as config_loader
from .experiment_registry import compute_manifest_canonical_bytes
from .manifest_signer import ManifestSigner, compute_body_hash, compute_key_fingerprint
from .route_helpers import build_default_manifest_payload


def _source(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve(strict=True)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build_signed_manifest(*, repo_root: Path, fixture: Path, key_file: Path, output: Path,
                          experiment_id: str, strategy: str = "ma_crossover", environment: str = "demo",
                          snapshot: Path | None = None, next_open: bool = False, taker_entry: bool = False,
                          full_chain: bool = False, starting_balance: float = 10000,
                          data_tier: str = "S2", run_id: str | None = None) -> dict[str, Any]:
    if environment not in ("demo", "paper", "live"):
        raise ValueError("unknown repository configuration environment")
    if not math.isfinite(starting_balance) or starting_balance <= 0:
        raise ValueError("starting_balance must be positive finite")
    if data_tier not in ("S1", "S2", "S3"):
        raise ValueError("unknown data tier")
    if not experiment_id.strip():
        raise ValueError("experiment_id is required")
    key_file = key_file.resolve(strict=True)
    output = output.resolve()
    fixture = fixture.resolve(strict=True)
    sources = []
    if snapshot is not None:
        params = json.loads(snapshot.read_text())
        sources.append(_source(snapshot))
        provenance_kind = "caller_snapshot"
    else:
        # 既有載入器以環境變數定位；僅在同步本機組裝期間覆寫並還原。
        old_root = os.environ.get("OPENCLAW_BASE_DIR")
        try:
            os.environ["OPENCLAW_BASE_DIR"] = str(repo_root.resolve(strict=True))
            params = {"strategy_params": config_loader.load_production_strategy_params_toml(engine=environment),
                      "risk_overrides": config_loader.load_production_risk_overrides_toml(engine=environment)}
            if full_chain:
                params["scanner_config"] = config_loader.load_production_scanner_config()
            paths = [repo_root / "settings" / f"strategy_params_{environment}.toml",
                     repo_root / "settings/risk_control_rules" / f"risk_config_{environment}.toml"]
            if full_chain:
                paths.append(repo_root / "settings/risk_control_rules/scanner_config.toml")
            sources.extend(_source(path) for path in paths)
        finally:
            if old_root is None:
                os.environ.pop("OPENCLAW_BASE_DIR", None)
            else:
                os.environ["OPENCLAW_BASE_DIR"] = old_root
        provenance_kind = "repository_config"
    for name in ("strategy_params", "risk_overrides") + (("scanner_config",) if full_chain else ()):
        if not isinstance(params.get(name), dict) or not params[name]:
            raise ValueError(f"{name} missing/invalid; no default fallback allowed")
    if not isinstance(params["risk_overrides"].get("limits"), dict) or not params["risk_overrides"]["limits"]:
        raise ValueError("risk_overrides.limits missing; partial snapshot is not a complete input")
    if not isinstance(params["strategy_params"].get(strategy), dict) or not params["strategy_params"][strategy]:
        raise ValueError("selected strategy parameters missing")
    params = copy.deepcopy(params)
    overrides = []
    if taker_entry:
        if strategy != "ma_crossover":
            raise ValueError("taker-entry override is only defined for ma_crossover")
        before = params["strategy_params"][strategy].get("use_maker_entry")
        params["strategy_params"][strategy]["use_maker_entry"] = False
        overrides.append({"path": "strategy_params.ma_crossover.use_maker_entry", "before": before,
                          "after": False, "reason": "R8 Stage 1 explicitly requests taker entry"})
    if next_open and strategy == "ma_crossover" and params["strategy_params"][strategy].get("use_maker_entry", True):
        raise ValueError("next-symbol-open with maker entry requires explicit --taker-entry")
    protected = {key_file, fixture, *(Path(s["path"]) for s in sources)}
    if output in protected or output.name == "key.hex":
        raise ValueError("output must not overwrite any input or signing key")
    fingerprint = compute_key_fingerprint(key_file.read_bytes())
    sibling = output.parent / "key.hex"
    if not sibling.is_file() or compute_key_fingerprint(sibling.read_bytes()) != fingerprint:
        raise ValueError("caller must provide matching key.hex beside output manifest")
    signer = ManifestSigner(key_file, fingerprint)
    body = build_default_manifest_payload(experiment_id=experiment_id, output_dir=output.parent, cur=None)
    body.update({"fixture_uri": str(fixture), "data_tier": data_tier, "strategy": strategy,
                 "strategy_params": params["strategy_params"], "risk_overrides": params["risk_overrides"],
                 "starting_balance": starting_balance, "include_replay_metadata": True,
                 "parameter_overrides": overrides,
                 "parameter_provenance": {"source_kind": provenance_kind, "environment": environment if snapshot is None else None,
                                          "runtime_effective_verified": False, "files": sources,
                                          "fixture": _source(fixture)}})
    if full_chain:
        body.update(mode="full_chain", scanner_config=params["scanner_config"])
    if next_open:
        body["execution_timing"] = "next_symbol_open"
    if run_id is not None:
        body["run_id"] = run_id
    canonical = compute_manifest_canonical_bytes(body)
    signed = {**body, "manifest_hash": compute_body_hash(canonical), "signature": signer.sign(canonical)}
    output.write_text(json.dumps(signed, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return signed
