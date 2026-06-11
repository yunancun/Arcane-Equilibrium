"""L2 P4 整合接線釘子：dual-path resolve 在整合樹上必須解析到「真」A 線模組。

為什麼需要本檔（E4 2026-06-11 整合回歸補洞）：
  test_l2_p4_online_fdr.py / test_l2_p3b_hypothesize.py /
  test_alpha_wealth_refund_reconciler.py 全部 monkeypatch resolve 點
  （_FakeAwc / lambda: None / sys.modules stub）——單線隔離正確，但整合樹上
  「真模組真的可被解析」一直沒有釘子。若 learning_engine 的 A 線模組被改名 /
  搬走 / import 壞掉，executor 與 reconciler 會走 fail-closed 分支
  （hypothesize 全 DEFER alpha_wealth_store_unavailable）：行為「誠實」但
  P4 整體靜默休眠，無任何測試變紅。本檔把 wiring 釘死，斷裂即紅。

不 mock 任何東西；只做 import 解析與純函數煙測（0 DB、0 IO）。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_SRV_ROOT = Path(__file__).resolve().parents[5]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))

from app import l2_candidate_evidence_adapter as ADAPTER  # noqa: E402
from app import l2_ml_advisory_executor as EXEC  # noqa: E402


def test_executor_resolves_real_alpha_wealth_controller() -> None:
    """executor dual-path 必須命中真 A 模組（非 None fail-closed 分支）。"""
    awc = EXEC._resolve_wealth_controller()
    assert awc is not None, (
        "integrated tree must resolve learning_engine.alpha_wealth_controller; "
        "None means P4 silently dormant (every hypothesize DEFERs)"
    )
    # M1 契約符號在場且型別正確（B/C 兩線 lazy 取用的全部字面）。
    assert isinstance(float(awc.PHI_REFUND), float)
    assert isinstance(int(awc.MIN_FORWARD_OOS_DAYS), int)
    assert callable(awc.demo_confirm_verdict)
    assert callable(awc.refund_amount)
    # 真值表煙測（純函數）：樣本不足 → pending；n 足 + not green → failed。
    assert awc.demo_confirm_verdict(
        n_trades=0, stage0r_green=True, demo_net_bps=1.0, forward_oos_days=30
    ) == "pending"
    assert awc.demo_confirm_verdict(
        n_trades=30, stage0r_green=False, demo_net_bps=1.0, forward_oos_days=30
    ) == "failed"


def test_adapter_resolves_real_n_eff_cluster() -> None:
    """adapter dual-path 必須命中真 n_eff_average_linkage（非 raw-K fallback）。"""
    fn = ADAPTER._resolve_n_eff_cluster()
    assert fn is not None, (
        "integrated tree must resolve learning_engine.n_eff_cluster; None means "
        "DSR deflation permanently falls back to raw k_trials"
    )
    # 真聚類煙測：兩條相同 25-bar 序列（> DEFAULT_MIN_OVERLAP_BARS=20，corr=1）
    # → 1 cluster → n_eff=1。鎖「真演算法在場」而非僅 import 成功。
    series = {i: ((-1.0) ** i) * 0.01 * (1 + i % 3) for i in range(25)}
    res = fn([dict(series), dict(series)])
    assert int(res.n_eff) == 1, res


def test_reconciler_loads_same_real_controller_module() -> None:
    """C 線 reconciler 的 _load_controller 必須解析到與 executor 同一個真模組。"""
    from program_code.ml_training import alpha_wealth_refund_reconciler as recon

    awc_exec = EXEC._resolve_wealth_controller()
    awc_recon = recon._load_controller()
    assert awc_recon is awc_exec, (
        "executor and reconciler must share the single A-line module "
        f"(got {getattr(awc_recon, '__name__', awc_recon)!r} vs "
        f"{getattr(awc_exec, '__name__', awc_exec)!r})"
    )
    loader = recon._default_round_trip_loader()
    assert loader.__module__.endswith("ml_training.residual_alpha_producer_db")
