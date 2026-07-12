"""Bybit 默認費率常數 — helper 離線分析腳本的單一 Python SSOT 錨點。

MODULE_NOTE:
  模塊用途：全 repo 的 helper / research / calibration / healthcheck 離線腳本
    先前各自硬編 taker 0.00055 / maker 0.0002（及其 bps 形式 5.5 / 2.0），任何
    一處改值都可能靜默漂移。本模組把這組字面值收斂為單一 Python 錨點；配套
    drift-guard 測試（``helper_scripts/lib/tests/test_fee_constants.py``）以
    regex 對 Rust 源與既有 Python 消費檔逐檔斷言等值，使「改值未同步全 repo」
    必定 CI fail-loud。
  權威邊界（重要，勿誤讀本模組地位）：
    - runtime 權威 = Rust ``account_manager``（per-symbol 動態費率，來源
      Bybit ``/v5/account/fee-rate``；未查到的 symbol 才回落
      ``DEFAULT_TAKER_FEE`` / ``DEFAULT_MAKER_FEE``）。
    - 外部政策錨 = ``docs/references/2026-04-04--bybit_api_reference.md``
      §AccountManager（taker 0.055% / maker 0.02% 默認）。
    - 本模組僅為 helper 離線分析常數 SSOT，不是交易 runtime 的費率來源，
      不得被 ``control_api_v1/app/`` runtime 模塊匯入。
  硬邊界：
    - 純常數層；無 DB / 無 IO / 無 live state。
    - bps 一律由 rate * 1e4 導出，禁二次硬編（防 rate 與 bps 各自漂移）。
    - TOML 與 Rust 明確不收斂到本模組（env 獨立規則 / runtime API 覆蓋）。
"""

from __future__ import annotations

# Bybit V5 linear perp 默認費率（rate 形式；與 Rust account_manager.rs 的
# DEFAULT_TAKER_FEE / DEFAULT_MAKER_FEE 及 grid_trading DEFAULT_FEE_PCT 等值）。
TAKER_FEE_RATE: float = 0.00055
MAKER_FEE_RATE: float = 0.0002

# bps 形式：由 rate 導出（禁在此處或下游二次硬編獨立字面值）。
TAKER_FEE_BPS: float = TAKER_FEE_RATE * 1e4  # = 5.5
MAKER_FEE_BPS: float = MAKER_FEE_RATE * 1e4  # = 2.0
