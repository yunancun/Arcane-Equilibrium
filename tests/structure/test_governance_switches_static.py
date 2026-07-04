"""
MODULE_NOTE
模塊用途：釘住 2026-07-04 冷審計 R2 D5 治理開關批的 TOML 收斂值，防止未來
  被靜默回滾（arm 決策=operator 裁決，回滾需再走 operator 決策）。
主要函數：test_cost_edge_demo_live_armed_paper_dormant、
  test_budget_cost_edge_max_ratio_converged_to_design_value。
依賴：settings/risk_control_rules/*.toml、budget_config.toml（repo 根，legacy
  快照）、tomllib（Python 3.11+ 標準庫）。
硬邊界：三環境 TOML 故意獨立（memory feedback_env_config_independence），
  本測試只釘各自的值，不主張任何跨環境合併。
"""

from __future__ import annotations

from pathlib import Path

# 鏡像 test_strategy_blocked_symbols_freeze.py 既有 pattern：3.11+ 用標準庫，
# 舊 runner 回退 tomli。
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[2]
RISK_DIR = REPO_ROOT / "settings" / "risk_control_rules"


def _load(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def test_cost_edge_demo_live_armed_paper_dormant() -> None:
    """D5：demo/live [cost_edge].enabled=true（advisory 腿 arm），paper 維持 dormant。

    為什麼釘死：enabled=true 是 operator 對冷審計 R2 P2-2 的顯式裁決
    （原則 #13 治理腿不得長期 dormant）；advisor 為 observation-only，
    env-gate OPENCLAW_COST_EDGE_ADVISOR 仍為第二道保險。
    """
    demo = _load(RISK_DIR / "risk_config_demo.toml")
    live = _load(RISK_DIR / "risk_config_live.toml")
    paper = _load(RISK_DIR / "risk_config_paper.toml")

    assert demo["cost_edge"]["enabled"] is True
    assert live["cost_edge"]["enabled"] is True
    # paper 未被 D5 覆蓋，維持 dormant（三環境獨立，不連帶重設）。
    assert paper["cost_edge"]["enabled"] is False

    # threshold 不因 arm 連帶改動（risk 參數改動限定範圍）。
    assert demo["cost_edge"]["trigger_threshold"] == -0.5
    assert live["cost_edge"]["trigger_threshold"] == -0.3
    assert paper["cost_edge"]["trigger_threshold"] == -0.5


def test_budget_cost_edge_max_ratio_converged_to_design_value() -> None:
    """D5：兩份 budget_config.toml 的 cost_edge_max_ratio 均為 MICRO-PROFIT-FIX-1
    設計值 0.2（配 min_profit_to_close_pct=0.3），不得回到 100.0（永不觸發）。

    為什麼：Rust 側範圍已縮至 [0, 10]（>10 由 legacy_migration clamp 回 default），
    檔內 100.0 是 Phase 5 legacy 殘留；收斂後檔值與 Rust default 同源。
    """
    for path in (
        REPO_ROOT / "budget_config.toml",  # legacy 快照（repo 根，非引擎默認載入路徑）
        RISK_DIR / "budget_config.toml",  # 引擎默認載入路徑（startup/mod.rs base 目錄）
    ):
        cfg = _load(path)
        at = cfg["attention_tax"]
        assert at["cost_edge_max_ratio"] == 0.2, f"{path}: {at['cost_edge_max_ratio']}"
        assert at["min_profit_to_close_pct"] == 0.3, f"{path}"
        # 防回歸下界：任何 >10 的值都會被 Rust 端 clamp，檔內不允許再出現。
        assert 0.0 < at["cost_edge_max_ratio"] <= 10.0
