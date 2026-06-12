"""AEG-S3 OI delta evidence producer 測試。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aeg_candidate_metrics import builder as candidate_builder
from aeg_s3_candidate_rows import builder as rows_builder
from aeg_s3_oi_delta import artifact as artifact_mod
from aeg_s3_oi_delta import builder as builder_mod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _raw_daily_panel() -> list[dict]:
    base = datetime(2026, 3, 1, tzinfo=timezone.utc)
    symbols = [f"SYM{i:02d}USDT" for i in range(12)]
    oi = {symbol: 1000.0 + idx * 100.0 for idx, symbol in enumerate(symbols)}
    price = {symbol: 100.0 + idx for idx, symbol in enumerate(symbols)}
    rows: list[dict] = []

    for day in range(-1, 65):
        ts = base + timedelta(days=day)
        for idx, symbol in enumerate(symbols):
            if day >= 0:
                if idx < 2:
                    delta = 0.050 + (day % 3) * 0.001
                    fwd_bps = 4.2 + (day % 5) * 0.08
                elif idx >= 10:
                    delta = -0.050 - (day % 2) * 0.001
                    fwd_bps = 1.4 - (day % 4) * 0.04
                else:
                    delta = (idx - 5.5) * 0.001
                    fwd_bps = 2.0 + (idx % 3) * 0.03
                oi[symbol] *= 1.0 + delta
                if day > -1:
                    price[symbol] *= 1.0 + fwd_bps / 10_000.0
            rows.append({
                "symbol": symbol,
                "ts_utc": ts.isoformat(),
                "open_interest": oi[symbol],
                "price": price[symbol],
            })
    return rows


def _pbo_test_grid() -> list[dict]:
    return [
        {
            "lookback_hours": lookback_hours,
            "horizon_hours": horizon_hours,
            "tail_frac": tail_frac,
            "min_symbols": 10,
            "cost_bps": 0.0,
            "side_mode": "long_high_short_low",
        }
        for lookback_hours in (24.0, 48.0, 72.0)
        for horizon_hours in (24.0, 48.0)
        for tail_frac in (0.15, 0.2)
    ]


def test_raw_panel_builds_oi_delta_evidence_consumed_by_s3_rows():
    evidence, summary = builder_mod.build_oi_delta_evidence(
        _raw_daily_panel(),
        source_path="fixture.jsonl",
        run_id="oi_run",
        lookback_hours=24,
        horizon_hours=24,
        cost_bps=11.0,
        k_trials=20,
        default_regime="chop",
        oos_start_date="2026-04-02",
    )

    assert summary["sample_count"] == 64
    assert summary["accepted_gross_bps_mean"] > 2.0
    assert summary["accepted_net_bps_mean"] < 0.0
    assert evidence["strategy_family"] == "oi_delta"
    assert evidence["daily_returns"]["policy"] == "sum_explicit_oi_delta_window_net_bps_by_sample_date"

    report, _s3_summary, _sample_rows, _daily_rows = rows_builder.build_direct_report(
        evidence,
        run_id="direct_run",
    )
    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="oi_delta",
        strategy_family="oi_delta",
        parameter_cell_id=evidence["parameter_cell_id"],
    )
    assert adapted["source_report_type"] == "aeg_candidate_metrics_direct"
    assert adapted["metric_status_counts"] == {"FAIL": 1}
    assert rows[0]["n_independent"] == 64
    assert rows[0]["net_bps"] < 0.0
    assert json.loads(rows[0]["reject_reasons"]) == ["missing_pbo"]


def test_candidate_grid_pbo_is_emitted_and_consumed_by_s3_rows():
    evidence, summary = builder_mod.build_oi_delta_evidence(
        _raw_daily_panel(),
        source_path="fixture.jsonl",
        run_id="oi_run",
        lookback_hours=24,
        horizon_hours=24,
        cost_bps=0.0,
        k_trials=12,
        default_regime="chop",
        oos_start_date="2026-04-02",
        pbo_grid=_pbo_test_grid(),
    )

    assert summary["pbo_status"] == "produced_candidate_grid"
    assert summary["pbo_grid_cell_count"] == 12
    assert summary["pbo_grid_included_candidate_count"] == 12
    assert len(evidence["pbo_candidates"]) == 12
    assert evidence["pbo_candidate_grid"][0]["included_in_pbo"] is True

    report, s3_summary, _sample_rows, _daily_rows = rows_builder.build_direct_report(
        evidence,
        run_id="direct_run",
    )
    assert s3_summary["pbo_status"] == "measured"

    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="oi_delta",
        strategy_family="oi_delta",
        parameter_cell_id=evidence["parameter_cell_id"],
    )
    assert adapted["source_report_type"] == "aeg_candidate_metrics_direct"
    assert rows[0]["pbo"] is not None
    assert "missing_pbo" not in json.loads(rows[0]["reject_reasons"])


def test_missing_regime_rejects_windows_instead_of_creating_unlabeled_regime():
    evidence, summary = builder_mod.build_oi_delta_evidence(
        _raw_daily_panel(),
        source_path="fixture.jsonl",
        run_id="oi_run",
        lookback_hours=24,
        horizon_hours=24,
        cost_bps=11.0,
        k_trials=20,
    )

    assert evidence["samples"] == []
    assert "daily_returns" not in evidence
    assert summary["window_reject_reasons"] == {"missing_regime": 64}


def test_precomputed_panel_rows_do_not_require_price_history():
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    payload = []
    for day in range(3):
        for idx in range(12):
            high = idx < 2
            low = idx >= 10
            payload.append({
                "symbol": f"SYM{idx:02d}USDT",
                "ts_utc": (base + timedelta(days=day)).isoformat(),
                "oi_delta_pct": 0.05 if high else (-0.05 if low else idx * 0.001),
                "forward_return_bps": 5.0 if high else (1.0 if low else 2.0),
                "regime": "bear",
            })

    evidence, summary = builder_mod.build_oi_delta_evidence(
        payload,
        source_path="precomputed.jsonl",
        run_id="precomputed",
        lookback_hours=24,
        horizon_hours=24,
        cost_bps=2.0,
        k_trials=6,
        min_symbols=10,
    )

    assert summary["sample_count"] == 3
    assert summary["row_reject_reasons"] == {}
    assert evidence["samples"][0]["gross_bps"] == 4.0
    assert evidence["samples"][0]["net_bps"] == 2.0


def test_min_spacing_rejects_overlapping_rebalance_windows():
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    payload = []
    for hour in range(6):
        for idx in range(12):
            payload.append({
                "symbol": f"SYM{idx:02d}USDT",
                "ts_utc": (base + timedelta(hours=hour)).isoformat(),
                "oi_delta_pct": idx / 100.0,
                "forward_return_bps": idx / 10.0,
                "regime": "chop",
            })

    evidence, summary = builder_mod.build_oi_delta_evidence(
        payload,
        source_path="hourly.jsonl",
        run_id="spacing",
        lookback_hours=1,
        horizon_hours=2,
        cost_bps=0.0,
        k_trials=6,
        min_symbols=10,
        min_spacing_hours=2,
    )

    assert summary["sample_count"] == 3
    assert summary["window_reject_reasons"] == {"overlap_spacing": 3}
    assert [row["sample_ts_utc"][11:13] for row in evidence["samples"]] == ["00", "02", "04"]


def test_artifact_write_creates_evidence_manifest_and_index(tmp_path):
    evidence, summary = builder_mod.build_oi_delta_evidence(
        _raw_daily_panel(),
        source_path="fixture.jsonl",
        run_id="oi_run",
        lookback_hours=24,
        horizon_hours=24,
        cost_bps=11.0,
        k_trials=20,
        default_regime="chop",
    )
    written = artifact_mod.write_all(
        evidence=evidence,
        summary=summary,
        run_id="oi_run",
        repo_root=Path("."),
        artifact_root=tmp_path / "out",
        created_by_role="PM",
    )

    run_dir = Path(written["run_dir"])
    direct_input = json.loads((run_dir / "oi_delta_candidate_evidence.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    assert direct_input["samples"]
    assert manifest["policy"] == "explicit_oi_delta_rebalance_windows_only_no_db_or_scalar_synthesis"
    assert any(entry["name"] == "oi_delta_candidate_evidence.json" for entry in index["artifacts"])


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_oi_delta"
    code = "\n".join(path.read_text(encoding="utf-8") for path in pkg.glob("*.py"))
    forbidden = (
        "control_api_v1",
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "OPENCLAW_ALLOW_MAINNET",
        "execution_authority",
        "wss://stream.bybit.com",
        "urlopen",
    )
    for needle in forbidden:
        assert needle not in code
