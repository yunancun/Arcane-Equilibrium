from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = ROOT / "sql" / "queries" / "w2_btc_alt_lead_lag_counterfactual.sql"


def test_w2_counterfactual_joins_use_minute_aligned_panel_bucket() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "snapshot_bucket_ts_ms" in sql
    assert "((pw.snapshot_ts_ms / 60000) * 60000)::BIGINT AS snapshot_bucket_ts_ms" in sql
    assert "ak.bucket_ts_ms = pe.snapshot_bucket_ts_ms" in sql
    assert "pf.bucket_ts_ms = pe.snapshot_bucket_ts_ms" in sql
    assert "ak.bucket_ts_ms = pe.snapshot_ts_ms" not in sql
    assert "pf.bucket_ts_ms = pe.snapshot_ts_ms" not in sql
