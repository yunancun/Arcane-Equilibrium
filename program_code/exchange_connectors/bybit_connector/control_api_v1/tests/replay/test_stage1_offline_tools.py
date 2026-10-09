"""R8 離線工具驗收；網路連線在每個測試封鎖。"""
import json
import socket
import sys
from pathlib import Path

import pytest

CONTROL_ROOT = Path(__file__).resolve().parents[2]
ROOT = CONTROL_ROOT.parents[3]
sys.path.insert(0, str(CONTROL_ROOT))
from replay.offline_analytics import analyze_report, crosses_funding


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("offline test attempted network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def fill(ts, side, qty, price, fee=0.0, symbol="BTCUSDT"):
    return dict(ts_ms=ts, effective_ts_ms=ts, side=side, qty=qty, price=price,
                fee=fee, symbol=symbol, slippage_bps=0, fill_status="filled")


def report(fills, net, end=None):
    return {"result": {"fills": fills, "pnl_summary": {"starting_balance":10000, "net_pnl":net},
                       "diagnostics": {}}, "stage1": {"replay_end_ts_ms": end}}


def test_analytics_three_term_reconciliation_and_unmatched_cost():
    result = analyze_report(report([fill(1,"long",2,100,0.2),fill(2,"short",1,110,0.1)],9.7,3))
    assert len(result["round_trips"]) == 1
    assert result["round_trips"][0]["net_pnl"] == pytest.approx(9.8)
    assert result["unmatched_fills"][0]["entry_fee"] == pytest.approx(0.1)
    assert result["reconciliation"]["residual"] == pytest.approx(0,abs=1e-12)
    assert result["equity_curve_available"] is False
    assert result["curve_kind"] == "realized_balance_only"


@pytest.mark.parametrize("start,end,expected", [(1,1000,False),(1,28800000,True),(28800000,28800001,True),
                                                (28800001,28800002,False),(1,86400001,True)])
def test_analytics_funding_endpoints(start,end,expected):
    assert crosses_funding(start,end,[0,8,16]) is expected


def test_analytics_open_position_sets_global_funding_flag():
    result = analyze_report(report([fill(1,"long",1,100,0.1)],-0.1,28800000))
    assert result["funding"]["completed_crossing_count"] == 0
    assert result["funding"]["open_position_crossing_count"] == 1
    assert result["funding"]["funding_crossed"] is True


def test_analytics_symbol_schedule_and_closed_intervals():
    result = analyze_report(report([fill(1,"short",1,100),fill(28800000,"long",1,90)],10,28800000),
                            funding_hours={"BTCUSDT":[4]})
    assert result["round_trips"][0]["crosses_funding"] is True
    assert result["round_trips"][0]["net_return_bps"] == 1000
    other = analyze_report(report([fill(1,"long",1,100),fill(100,"short",1,100)],0,100))
    assert other["funding"]["funding_crossed"] is False


def test_analytics_weighted_additions_partial_closes_keep_earliest_lot():
    fills = [fill(1,"long",1,100,0.1), fill(28799999,"long",1,120,0.1), fill(28800001,"short",1,130,0.1)]
    result = analyze_report(report(fills,19.7,28800002))
    assert result["round_trips"][0]["entry_price"] == 110
    assert len(result["round_trips"][0]["holding_intervals"]) == 2
    assert result["funding"]["open_position_crossing_count"] == 1
    assert result["unmatched_fills"][0]["entry_fee"] == pytest.approx(0.1)


def test_analytics_zero_rows_are_not_trades():
    rows=[{**fill(i,"long",0,0),"fill_status":"rejected"} for i in range(14)]
    result=analyze_report(report(rows,0,100))
    assert result["round_trips"] == []
    assert result["zero_quantity_reasons"] == {"rejected":14}


def test_analytics_slippage_is_not_deducted_twice():
    result=analyze_report(report([{**fill(1,"long",1,100.05),"slippage_bps":5},
                                 {**fill(2,"short",1,109.945),"slippage_bps":-5}],9.895,3))
    assert result["costs"]["slippage_cost"] == pytest.approx(.105)
    assert result["round_trips"][0]["net_pnl"] == pytest.approx(9.895)


@pytest.mark.parametrize("mode", ["missing_end","early_end","residual","over_close"])
def test_analytics_incomplete_reports_fail_closed(mode):
    p=report([fill(10,"long",1,100)],0,20)
    if mode == "missing_end": p["stage1"]={}
    if mode == "early_end": p["stage1"]["replay_end_ts_ms"]=1
    if mode == "residual": p["result"]["pnl_summary"]["net_pnl"]=1
    if mode == "over_close": p["result"]["fills"].append(fill(11,"short",2,100))
    with pytest.raises(ValueError): analyze_report(p)


@pytest.fixture
def manifest_args(tmp_path):
    fixture=tmp_path/"fixture.json"
    fixture.write_text(json.dumps({"schema_version":1,"events":[dict(ts_ms=1,symbol="BTCUSDT",open=100,high=100,low=100,close=100,volume=1)]}))
    key=tmp_path/"key.hex"
    # 測試私有目錄中的測試金鑰；工具本身不產生金鑰。
    key.write_text("ab"*32+"\n")
    return dict(repo_root=ROOT,fixture=fixture,key_file=key,output=tmp_path/"manifest.json",experiment_id="r8-test")


def test_manifest_demo_preserved_and_deterministic(manifest_args):
    from replay.offline_manifest import build_signed_manifest
    first=build_signed_manifest(**manifest_args)
    before=manifest_args["output"].read_bytes()
    second=build_signed_manifest(**manifest_args)
    assert before == manifest_args["output"].read_bytes()
    assert first == second
    assert first["strategy_params"]["ma_crossover"]["use_maker_entry"] is True
    assert first["parameter_provenance"]["source_kind"] == "repository_config"
    assert len(first["parameter_provenance"]["files"]) == 2
    assert first["parameter_provenance"]["runtime_effective_verified"] is False


def test_manifest_override_signed_and_maker_next_rejected(manifest_args):
    from replay.offline_manifest import build_signed_manifest
    from replay.experiment_registry import compute_manifest_canonical_bytes
    from replay.manifest_signer import ManifestSigner, compute_key_fingerprint
    with pytest.raises(ValueError,match="taker-entry"):
        build_signed_manifest(**manifest_args,next_open=True)
    result=build_signed_manifest(**manifest_args,next_open=True,taker_entry=True)
    assert result["parameter_overrides"][0]["before"] is True
    assert result["parameter_overrides"][0]["after"] is False
    body={k:v for k,v in result.items() if k not in ("signature","manifest_hash")}
    signer=ManifestSigner(manifest_args["key_file"],compute_key_fingerprint(manifest_args["key_file"].read_bytes()))
    assert signer.sign(compute_manifest_canonical_bytes(body)) == result["signature"]


def test_manifest_snapshot_provenance_and_no_defaults(manifest_args):
    from replay.offline_manifest import build_signed_manifest
    original=build_signed_manifest(**manifest_args)
    snapshot=manifest_args["output"].parent/"snapshot.json"
    snapshot.write_text(json.dumps({k:original[k] for k in ("strategy_params","risk_overrides")}))
    result=build_signed_manifest(**manifest_args,snapshot=snapshot)
    assert result["parameter_provenance"]["source_kind"] == "caller_snapshot"
    assert result["parameter_provenance"]["files"][0]["path"] == str(snapshot)
    snapshot.write_text('{"strategy_params":{}}')
    with pytest.raises(ValueError,match="fallback"): build_signed_manifest(**manifest_args,snapshot=snapshot)


def test_manifest_missing_config_is_error(manifest_args,tmp_path):
    from replay.offline_manifest import build_signed_manifest
    manifest_args["repo_root"]=tmp_path
    with pytest.raises((ValueError,OSError)): build_signed_manifest(**manifest_args)


def test_manifest_key_path_closed_and_never_overwritten(manifest_args,tmp_path):
    from replay.offline_manifest import build_signed_manifest
    key=manifest_args["key_file"]; original=key.read_bytes()
    manifest_args["output"]=key
    with pytest.raises(ValueError): build_signed_manifest(**manifest_args)
    assert key.read_bytes() == original
    sub=tmp_path/"other";sub.mkdir();manifest_args["output"]=sub/"manifest.json"
    with pytest.raises(ValueError,match="key.hex"): build_signed_manifest(**manifest_args)


def test_manifest_full_chain_requires_scanner(manifest_args):
    from replay.offline_manifest import build_signed_manifest
    result=build_signed_manifest(**manifest_args,full_chain=True)
    assert result["mode"] == "full_chain" and result["scanner_config"]
    assert len(result["parameter_provenance"]["files"]) == 3

@pytest.mark.parametrize("key", ["qty","price","fee","slippage_bps"])
def test_analytics_nonfinite_numbers_fail_closed(key):
    row=fill(1,"long",1,100);row[key]=float("nan")
    with pytest.raises(ValueError): analyze_report(report([row],0,2))

def test_manifest_rejects_partial_risk_snapshot(manifest_args):
    from replay.offline_manifest import build_signed_manifest
    original=build_signed_manifest(**manifest_args)
    snapshot=manifest_args["output"].parent/"partial.json"
    snapshot.write_text(json.dumps({"strategy_params":original["strategy_params"],"risk_overrides":{"unknown":1}}))
    with pytest.raises(ValueError,match="limits"): build_signed_manifest(**manifest_args,snapshot=snapshot)
