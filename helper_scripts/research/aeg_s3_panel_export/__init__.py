"""AEG-S3 offline panel exporter.

MODULE_NOTE:
  模塊用途：把 V125/V127 read-only storage 匯出成 AEG-S3 producer 可消費的
    offline JSONL panel。此 package 本身不判斷 alpha、不產 promotion proof。
  邊界：artifact/export only；data_loader 只 SELECT；builder 純函數。
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_panel_export.v0.1"
SUMMARY_SCHEMA_VERSION = "aeg.s3_panel_export_summary.v0.1"

DEFAULT_ALPHA_HISTORY_RUN_ID = "18b3c2f8-6125-42a8-a42c-cfcc8aec9406"
DEFAULT_REGIME_CLASSIFIER_VERSION = "aeg_regime_v0.1.0"
DEFAULT_UNIVERSE = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "TRXUSDT", "BCHUSDT", "NEARUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "TONUSDT", "POLUSDT",
)

__all__ = [
    "DEFAULT_ALPHA_HISTORY_RUN_ID",
    "DEFAULT_REGIME_CLASSIFIER_VERSION",
    "DEFAULT_UNIVERSE",
    "RUNNER_VERSION",
    "SUMMARY_SCHEMA_VERSION",
]
