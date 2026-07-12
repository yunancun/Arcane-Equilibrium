"""跨語言費率常數 drift-guard — helper_scripts.lib.fee_constants。

MODULE_NOTE:
  模塊用途：fee_constants 是 helper 離線腳本的費率 SSOT 錨點，但 runtime 權威
    在 Rust（account_manager per-symbol /v5/account/fee-rate 回落 DEFAULT_*），
    且既有 13 個 Python 消費檔仍各自持有字面常數（follow-up ticket 才逐檔改
    import）。本測試以 regex 直讀各源檔字面值並斷言 == fee_constants，消滅
    「任何一處改值未同步全 repo 可靜默漂移」的性質：改了 Rust / 任一消費檔 /
    fee_constants 其中之一而未同步其餘 → 本測試 CI fail-loud。
  覆蓋面：
    - Rust×2：account_manager.rs DEFAULT_TAKER_FEE / DEFAULT_MAKER_FEE、
      grid_trading/mod.rs DEFAULT_FEE_PCT。
    - Python×13 消費檔：見 _PY_LITERAL_CHECKS 表（每列=檔案+regex+期望值）。
  依賴：pytest + 純 stdlib（re / pathlib）。無 DB / 無 IO 副作用（只讀源檔）。

  執行：``python3 -m pytest helper_scripts/lib/tests/test_fee_constants.py -q``
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from helper_scripts.lib import fee_constants as FC

# repo root = srv/（本檔位於 helper_scripts/lib/tests/ 之下三層）
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _extract(rel_path: str, pattern: str) -> float:
    """讀源檔並以 regex 抽出唯一字面常數；抽不到即 fail-loud（防 regex 腐化）。"""
    path = _REPO_ROOT / rel_path
    assert path.is_file(), f"drift-guard 目標檔不存在（被移動/改名須同步本測試）: {rel_path}"
    text = path.read_text(encoding="utf-8")
    m = re.search(pattern, text)
    assert m is not None, (
        f"drift-guard regex 在 {rel_path} 抽不到常數（pattern={pattern!r}）；"
        "若該檔已改為 import fee_constants，請把該列自 _PY_LITERAL_CHECKS 移除"
    )
    return float(m.group(1))


# ── SSOT 自身一致性 ────────────────────────────────────────────────────────


def test_ssot_bps_derived_from_rate():
    # bps 必須由 rate * 1e4 導出且數值精確（0.00055/0.0002 的 *1e4 在 IEEE754
    # 下恰好精確等於 5.5/2.0，已驗證）；禁二次硬編。
    assert FC.TAKER_FEE_BPS == FC.TAKER_FEE_RATE * 1e4 == 5.5
    assert FC.MAKER_FEE_BPS == FC.MAKER_FEE_RATE * 1e4 == 2.0
    assert FC.TAKER_FEE_RATE > FC.MAKER_FEE_RATE > 0.0


# ── Rust 源錨點（runtime 權威側的默認值） ──────────────────────────────────


def test_rust_account_manager_defaults_match():
    taker = _extract(
        "rust/openclaw_engine/src/account_manager.rs",
        r"const DEFAULT_TAKER_FEE: f64 = ([0-9.]+);",
    )
    maker = _extract(
        "rust/openclaw_engine/src/account_manager.rs",
        r"const DEFAULT_MAKER_FEE: f64 = ([0-9.]+);",
    )
    assert taker == FC.TAKER_FEE_RATE
    assert maker == FC.MAKER_FEE_RATE


def test_rust_grid_trading_default_fee_pct_matches():
    fee_pct = _extract(
        "rust/openclaw_engine/src/strategies/grid_trading/mod.rs",
        r"pub\(crate\) const DEFAULT_FEE_PCT: f64 = ([0-9.]+);",
    )
    assert fee_pct == FC.TAKER_FEE_RATE


# ── Python 消費檔字面常數（follow-up 改 import 前的過渡期守護） ─────────────
# 每列 = (相對路徑, regex（group 1=字面值）, 期望值)。任一檔改值未同步 → fail。

_PY_LITERAL_CHECKS: list[tuple[str, str, float]] = [
    # passive_wait_healthcheck
    (
        "helper_scripts/db/passive_wait_healthcheck/checks_execution.py",
        r"^TAKER_FEE_RATE = ([0-9.]+)$",
        FC.TAKER_FEE_RATE,
    ),
    (
        "helper_scripts/db/passive_wait_healthcheck/checks_execution.py",
        r"^MAKER_FEE_RATE = ([0-9.]+)$",
        FC.MAKER_FEE_RATE,
    ),
    (
        "helper_scripts/db/passive_wait_healthcheck/checks_pricing_binding.py",
        r"^DEFAULT_TAKER_FEE: float = ([0-9.]+)$",
        FC.TAKER_FEE_RATE,
    ),
    (
        "helper_scripts/db/passive_wait_healthcheck/checks_pricing_binding.py",
        r"^DEFAULT_MAKER_FEE: float = ([0-9.]+)$",
        FC.MAKER_FEE_RATE,
    ),
    # learning
    (
        "helper_scripts/learning/lg5_re_evaluate_pending.py",
        r"^_TAKER_FEE_RATE: float = ([0-9.]+)$",
        FC.TAKER_FEE_RATE,
    ),
    # calibration
    (
        "helper_scripts/calibration/phase_1b_maker_price.py",
        r"^TAKER_FEE_BPS = ([0-9.]+)",
        FC.TAKER_FEE_BPS,
    ),
    (
        "helper_scripts/calibration/phase_1b_maker_price.py",
        r"^MAKER_FEE_BPS = ([0-9.]+)",
        FC.MAKER_FEE_BPS,
    ),
    (
        # get_taker_baseline_fee_bps 的 fail-closed fallback（fn 內第一個
        # 「return <數字字面>」即該 fallback；動態查詢路徑 return float(row[0])
        # 不會被 [0-9.]+ 匹配）。
        "helper_scripts/calibration/phase_1b_tick_loader.py",
        r"def get_taker_baseline_fee_bps[\s\S]*?return ([0-9.]+)",
        FC.TAKER_FEE_BPS,
    ),
    # research cost models
    (
        "helper_scripts/research/funding_tilt_diagnostic/cost_model.py",
        r"^TAKER_FEE_BPS_PER_SIDE = ([0-9.]+)",
        FC.TAKER_FEE_BPS,
    ),
    (
        "helper_scripts/research/funding_tilt_diagnostic/cost_model.py",
        r"^MAKER_FEE_BPS_PER_SIDE = ([0-9.]+)",
        FC.MAKER_FEE_BPS,
    ),
    (
        "helper_scripts/research/multiday_trend_diagnostic/cost_model.py",
        r"^TAKER_FEE_BPS_PER_SIDE = ([0-9.]+)",
        FC.TAKER_FEE_BPS,
    ),
    (
        "helper_scripts/research/multiday_trend_diagnostic/cost_model.py",
        r"^MAKER_FEE_BPS_PER_SIDE = ([0-9.]+)",
        FC.MAKER_FEE_BPS,
    ),
    (
        "helper_scripts/research/cost_gate_learning_lane/cost_model.py",
        r"^FEE_TAKER_BPS = ([0-9.]+)",
        FC.TAKER_FEE_BPS,
    ),
    (
        "helper_scripts/research/cost_bleed_decomposition/decompose.py",
        r"^_FALLBACK_TAKER_FEE_BPS = ([0-9.]+)",
        FC.TAKER_FEE_BPS,
    ),
    (
        "helper_scripts/research/cost_bleed_decomposition/decompose.py",
        r"^_FALLBACK_MAKER_FEE_BPS = ([0-9.]+)",
        FC.MAKER_FEE_BPS,
    ),
    # canary
    (
        "helper_scripts/canary/replay_funding_harvest.py",
        r"^\s*perp_fee_bps_per_side = ([0-9.]+)",
        FC.TAKER_FEE_BPS,
    ),
    # counterfactual replay CLI default（flag 名後第一個 default=<數字>）
    (
        "helper_scripts/db/counterfactual_exit_replay.py",
        r"\"--fee-bps-per-side\",[\s\S]*?default=([0-9.]+),",
        FC.TAKER_FEE_BPS,
    ),
    # program_code
    (
        "program_code/local_model_tools/backtest_types.py",
        r"fee_rate_taker: float = ([0-9.]+)",
        FC.TAKER_FEE_RATE,
    ),
    (
        "program_code/local_model_tools/backtest_types.py",
        r"fee_rate_maker: float = ([0-9.]+)",
        FC.MAKER_FEE_RATE,
    ),
    (
        "program_code/ml_training/mlde_demo_applier.py",
        r"^_TAKER_FEE_RATE: float = ([0-9.]+)",
        FC.TAKER_FEE_RATE,
    ),
]


@pytest.mark.parametrize(
    "rel_path, pattern, expected",
    _PY_LITERAL_CHECKS,
    ids=[f"{p.split('/')[-1]}:{e}" for p, _, e in _PY_LITERAL_CHECKS],
)
def test_python_consumer_literal_matches(rel_path: str, pattern: str, expected: float):
    # ^…$ 錨定需 MULTILINE；跨行 pattern（[\s\S]）不受影響。
    path = _REPO_ROOT / rel_path
    assert path.is_file(), f"消費檔不存在（被移動/改名須同步本測試）: {rel_path}"
    text = path.read_text(encoding="utf-8")
    m = re.search(pattern, text, re.MULTILINE)
    assert m is not None, (
        f"drift-guard regex 在 {rel_path} 抽不到常數（pattern={pattern!r}）；"
        "若該檔已改為 import fee_constants，請把該列自 _PY_LITERAL_CHECKS 移除"
    )
    literal = float(m.group(1))
    assert literal == expected, (
        f"{rel_path} 字面費率 {literal} != SSOT {expected}"
        "（helper_scripts/lib/fee_constants.py）；改值必須全 repo 同步"
    )
