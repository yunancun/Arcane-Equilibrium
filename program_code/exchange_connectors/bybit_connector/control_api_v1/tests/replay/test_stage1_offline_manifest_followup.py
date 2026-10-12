"""U3：資料層與輸出硬連結保護；所有可寫輸入皆置於測試暫存目錄。"""
import json
import os
import shutil
import socket
import sys
from pathlib import Path

import pytest

CONTROL_ROOT = Path(__file__).resolve().parents[2]
ROOT = CONTROL_ROOT.parents[3]
sys.path.insert(0, str(CONTROL_ROOT))
from replay.offline_manifest import build_signed_manifest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("offline test attempted network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def args(tmp_path):
    repo = tmp_path / "repo"
    for relative in ("settings/strategy_params_demo.toml", "settings/risk_control_rules/risk_config_demo.toml"):
        dest = repo / relative; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, dest)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"schema_version": 1, "events": [dict(ts_ms=1, symbol="BTCUSDT", open=100, high=101, low=99, close=100, volume=1)]}))
    key = tmp_path / "key.hex"; key.write_text("ab" * 32 + "\n")
    return dict(repo_root=repo, fixture=fixture, key_file=key, output=tmp_path / "manifest.json", experiment_id="u3-test")


@pytest.mark.parametrize("tier,source,accepted", [
    ("S2", "s3_synthetic", False), ("S3", "s2_bybit_public", False),
    ("S2", "s2_bybit_public", True), ("S2", "s2_bybit_public_full_chain", True),
    ("S3", "s3_synthetic", True), ("S2", None, True), ("S3", None, True),
])
def test_source_tier_validation(args, tier, source, accepted):
    fixture = json.loads(args["fixture"].read_text())
    if source is not None: fixture["source"] = source
    args["fixture"].write_text(json.dumps(fixture))
    if not accepted:
        with pytest.raises(ValueError, match="source.*data_tier"):
            build_signed_manifest(**args, data_tier=tier)
        assert not args["output"].exists()
    else:
        signed = build_signed_manifest(**args, data_tier=tier)
        assert signed["data_tier"] == tier
        assert "source" not in signed
        assert signed == json.loads(args["output"].read_text())
        before = args["output"].read_bytes()
        build_signed_manifest(**args, data_tier=tier)
        assert args["output"].read_bytes() == before


@pytest.mark.parametrize("target", ["key", "fixture", "snapshot", "strategy_config", "risk_config"])
def test_output_hardlink_never_overwrites_input(args, target):
    signed = build_signed_manifest(**args)
    args["output"].unlink()
    if target == "snapshot":
        snapshot = args["fixture"].parent / "snapshot.json"
        snapshot.write_text(json.dumps({key: signed[key] for key in ("strategy_params", "risk_overrides")}))
        args["snapshot"] = snapshot; protected = snapshot
    elif target == "key": protected = args["key_file"]
    elif target == "fixture": protected = args["fixture"]
    else:
        protected = args["repo_root"] / ("settings/strategy_params_demo.toml" if target == "strategy_config" else "settings/risk_control_rules/risk_config_demo.toml")
    before = protected.read_bytes()
    os.link(protected, args["output"])
    assert args["output"].samefile(protected)
    with pytest.raises(ValueError, match="overwrite"):
        build_signed_manifest(**args)
    assert protected.read_bytes() == before
    assert args["output"].read_bytes() == before


def test_output_hardlink_to_distinct_matching_sibling_key_is_rejected(args):
    output_dir = args["fixture"].parent / "output"
    output_dir.mkdir()
    sibling = output_dir / "key.hex"
    sibling.write_bytes(args["key_file"].read_bytes())
    assert not sibling.samefile(args["key_file"])
    args["output"] = output_dir / "manifest.json"
    os.link(sibling, args["output"])
    before = sibling.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        build_signed_manifest(**args)
    assert sibling.read_bytes() == before
    assert args["key_file"].read_bytes() == before
    assert args["output"].read_bytes() == before
