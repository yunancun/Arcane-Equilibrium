#!/usr/bin/env python3
"""Smoke test — Alpha Tournament Candidate Stage 0R Runner（Track B）。

MODULE_NOTE
模塊用途：對 candidate_stage0r_runner + a2_cascade_adapter 的純合成數據驗證。
為什麼用合成數據而非 PG dry-run：PG empirical 留給 E4 regression（Linux ssh）；
本檔僅驗 (1) A2 functional 路徑能跑出 packet (2) 6-check 三態結構 (3)
sample_sufficiency split (4) A1 functional/fallback split (5) AMD §3.2 forbidden-output
紀律 (6) k_total override DSR 重算 (fast vs raw equivalence) (7) time-block
CSCV PBO 行為。

主要 cases：
  - A2 happy-ish path：合成 2-symbol 過 threshold rows → packet 結構完整。
  - A2 sample_insufficient：少樣本 → observe_more（非 reject）。
  - A1 functional：basis/funding rows 可用時不走 stale stub，且 net_bps 含 funding carry。
  - A1 fallback：source unavailable 時才標 basis_panel_infra_missing + infra_gap=True。
  - forbidden-output assert：整 packet JSON 0 hit forbidden token（AMD §3.2）。
  - k_total override：DSR 用 candidate k_total（4+k_prior）非 8c 291600 inflation。
  - time-block CSCV：≥4 days → pbo 非 None；<4 days → pbo None observe_more。
  - per-symbol threshold filter：BTC/ETH 不同 threshold 正確過濾。

依賴：純 stdlib + sibling adapter + runner（透過 sibling import w_audit_8c/8b）。
硬邊界：合成數據；不接 PG；不寫文件（除 JSON roundtrip in-memory）。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# sibling import 補位（直接執行路徑）。
_HERE = Path(__file__).resolve().parent
for _sub in (_HERE, _HERE.parent / "w_audit_8c", _HERE.parent / "w_audit_8b"):
    if str(_sub) not in sys.path:
        sys.path.insert(0, str(_sub))

try:
    from .a2_cascade_adapter import (  # type: ignore
        A2_ALPHA_SOURCE_ID,
        A2_K_NEW_CANDIDATE,
        A2CandidateConfig,
        run_a2_candidate,
    )
    from .candidate_stage0r_runner import (  # type: ignore
        A1_BASIS_INFRA_MISSING_REASON,
        A1_BASIS_PREREQ_TICKET,
        A1_ALPHA_SOURCE_ID,
        A1_HOLD_HOURS,
        a1_candidate_packet,
        a1_draft_only_packet,
        run_candidates,
        _time_block_cscv_pbo,
        _classify_sample_sufficiency,
    )
    from .candidate_stage0r_report import (  # type: ignore
        fetch_k_prior,
        _apply_k_prior_to_packet,
    )
except ImportError:
    from a2_cascade_adapter import (  # type: ignore
        A2_ALPHA_SOURCE_ID,
        A2_K_NEW_CANDIDATE,
        A2CandidateConfig,
        run_a2_candidate,
    )
    from candidate_stage0r_runner import (  # type: ignore
        A1_BASIS_INFRA_MISSING_REASON,
        A1_BASIS_PREREQ_TICKET,
        A1_ALPHA_SOURCE_ID,
        A1_HOLD_HOURS,
        a1_candidate_packet,
        a1_draft_only_packet,
        run_candidates,
        _time_block_cscv_pbo,
        _classify_sample_sufficiency,
    )
    from candidate_stage0r_report import (  # type: ignore
        fetch_k_prior,
        _apply_k_prior_to_packet,
    )


# ──────────────────────────────────────────────────────────────────────────
# 合成 8c SQL row builder（match 8c features.sql 輸出 schema）
# ──────────────────────────────────────────────────────────────────────────

_BASE_MS = int(datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)


def _row(
    *,
    symbol: str,
    day_offset: int,
    minute_offset: int,
    direction: str,         # long_liquidated / short_liquidated
    cluster_notional: float,
    fwd_bps: float,
    cost_bps: float = 12.0,
    event_count: int = 5,
) -> dict[str, Any]:
    """合成一個 8c final_signals row（含 net_bps）。

    expected_dir：long_liquidated → +1（mean-revert up）；short_liquidated → -1。
    net_bps = expected_dir × fwd 已隱含於 fwd_bps（caller 傳已 signed gross），
    這裡簡化為 gross = fwd_bps，net = gross - cost。
    """
    ts_ms = _BASE_MS + day_offset * 86_400_000 + minute_offset * 60_000
    expected_dir = 1 if direction == "long_liquidated" else -1
    # entry/exit mid：用 gross_bps 反推（10000 × dir × (exit-entry)/entry = fwd_bps）。
    entry_mid = 100.0
    exit_mid = entry_mid * (1.0 + (expected_dir * fwd_bps) / 10000.0)
    gross_bps = 10000.0 * expected_dir * (exit_mid - entry_mid) / entry_mid
    return {
        "symbol": symbol,
        "bucket_5m_epoch": ts_ms // 1000 // 300 * 300,
        "bucket_end_ts_ms": ts_ms,
        "dominant_side": direction,
        "expected_dir": expected_dir,
        "event_count_5m": event_count,
        "cluster_notional_5m": cluster_notional,
        "long_notional_5m": cluster_notional if direction == "long_liquidated" else 0.0,
        "short_notional_5m": cluster_notional if direction == "short_liquidated" else 0.0,
        "long_event_count": event_count if direction == "long_liquidated" else 0,
        "short_event_count": event_count if direction == "short_liquidated" else 0,
        "dominant_event_count": event_count,
        "side_dominance_ratio": 1.0,
        "notional_pct_24h": 0.99,
        "entry_mid": entry_mid,
        "exit_mid": exit_mid,
        "gross_bps": gross_bps,
        "net_bps": gross_bps - cost_bps,
    }


def _build_a2_panel(*, n_days: int, per_day: int, fwd_bps: float, btc_notional: float, eth_notional: float) -> list[dict[str, Any]]:
    """合成 A2 panel：BTC/ETH 各 n_days × per_day rows（雙方向交替）。"""
    rows: list[dict[str, Any]] = []
    for d in range(n_days):
        for i in range(per_day):
            direction = "long_liquidated" if i % 2 == 0 else "short_liquidated"
            rows.append(_row(symbol="BTCUSDT", day_offset=d, minute_offset=i * 7,
                             direction=direction, cluster_notional=btc_notional, fwd_bps=fwd_bps))
            rows.append(_row(symbol="ETHUSDT", day_offset=d, minute_offset=i * 7 + 3,
                             direction=direction, cluster_notional=eth_notional, fwd_bps=fwd_bps))
    return rows


def _a1_row(
    *,
    symbol: str,
    day_offset: int,
    funding_rate_bps: float = 20.0,
    basis_pct: float = 0.10,
    price_gross_bps: float = -10.0,
    funding_carry_bps: float = 40.0,
    cost_bps: float = 22.0,
) -> dict[str, Any]:
    """合成一個 A1 SQL row；net 必含 funding carry."""
    ts_ms = _BASE_MS + day_offset * 86_400_000
    return {
        "symbol": symbol,
        "signal_ts_ms": ts_ms,
        "funding_snapshot_ts_ms": ts_ms - 60_000,
        "funding_rate_bps": funding_rate_bps,
        "funding_annualized": funding_rate_bps / 10_000.0 * 1095.0,
        "basis_snapshot_ts_ms": ts_ms - 60_000,
        "basis_pct": basis_pct,
        "exit_ts_ms": ts_ms + A1_HOLD_HOURS * 3_600_000,
        "price_gross_bps": price_gross_bps,
        "funding_carry_bps": funding_carry_bps,
        "funding_settlement_count": 3,
        "net_bps": price_gross_bps + funding_carry_bps - cost_bps,
    }


def _build_a1_panel(*, n_days: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in range(n_days):
        rows.append(_a1_row(symbol="BTCUSDT", day_offset=d))
        rows.append(_a1_row(symbol="ETHUSDT", day_offset=d, funding_carry_bps=45.0))
    return rows


# ──────────────────────────────────────────────────────────────────────────
# checks
# ──────────────────────────────────────────────────────────────────────────

# AMD §3.2 forbidden output token（整 packet JSON 不得出現）。
_FORBIDDEN_TOKENS = [
    "Stage 1 PASS",
    "stage_1_pass",
    "auto_promote",
    "to_stage",
    "live_reserved",
    "max_retries",
    "live_execution_allowed",
    "OPENCLAW_ALLOW_MAINNET",
    "authorization.json",
    "execution_authority",
    "decision_lease_emitted",
]


def _check_a2_packet_structure(failures: list[str]) -> None:
    panel = _build_a2_panel(n_days=6, per_day=4, fwd_bps=40.0,
                            btc_notional=600_000.0, eth_notional=400_000.0)
    cfg = A2CandidateConfig()
    res = run_a2_candidate(panel, cfg, total_bucket_count=1478)
    if res.get("alpha_source_id") != A2_ALPHA_SOURCE_ID:
        failures.append(f"a2 alpha_source_id 錯: {res.get('alpha_source_id')}")
    if res.get("path") != "8c_per_event_adapter":
        failures.append(f"a2 path 錯: {res.get('path')}")
    if res.get("exit_model") != "fixed_horizon_60m_conservative_proxy":
        failures.append("a2 exit_model proxy 標註缺失")
    if "dynamic_exit_not_modeled" not in res or not res["dynamic_exit_not_modeled"]:
        failures.append("a2 dynamic_exit_not_modeled 缺失")
    if "packet_8c" not in res:
        failures.append("a2 packet_8c 缺失")


def _check_k_total_override(failures: list[str]) -> None:
    """adapter (a)：DSR 用 candidate k_total（4+k_prior）非 8c 291600 inflation。"""
    panel = _build_a2_panel(n_days=6, per_day=4, fwd_bps=40.0,
                            btc_notional=600_000.0, eth_notional=400_000.0)
    cfg = A2CandidateConfig(k_prior=10)
    res = run_a2_candidate(panel, cfg, total_bucket_count=1478)
    ov = res.get("dsr_override") or {}
    if ov.get("k_candidate_new") != A2_K_NEW_CANDIDATE:
        failures.append(f"k_candidate_new 錯: {ov.get('k_candidate_new')} != {A2_K_NEW_CANDIDATE}")
    if ov.get("k_candidate_total") != 10 + A2_K_NEW_CANDIDATE:
        failures.append(f"k_candidate_total 錯: {ov.get('k_candidate_total')}")
    # 8c inflated 必 ≫ candidate（max(25,n)×11664 = 291600 量級）。
    inflated = ov.get("k_8c_inflated_total") or 0
    if inflated < 100_000:
        failures.append(f"8c inflated k_total 異常低（override 驗證失效）: {inflated}")
    # packet_8c.k_total 應已被 override 為 candidate 值。
    packet = res.get("packet_8c") or {}
    if packet.get("k_total") != 10 + A2_K_NEW_CANDIDATE:
        failures.append(f"packet_8c.k_total 未被 override: {packet.get('k_total')}")
    # 8c inflated DSR 被保存（透明度）。
    if "dsr_8c_inflated_preserved" not in packet:
        failures.append("dsr_8c_inflated_preserved 未保存（透明度缺）")


def _check_per_symbol_threshold_filter(failures: list[str]) -> None:
    """per-symbol threshold：BTC $500k / ETH $300k 正確過濾。"""
    # BTC 580k（過 500k）/ ETH 280k（不過 300k）。
    rows = [
        _row(symbol="BTCUSDT", day_offset=0, minute_offset=0, direction="long_liquidated",
             cluster_notional=580_000.0, fwd_bps=40.0),
        _row(symbol="ETHUSDT", day_offset=0, minute_offset=3, direction="long_liquidated",
             cluster_notional=280_000.0, fwd_bps=40.0),
    ]
    cfg = A2CandidateConfig()
    res = run_a2_candidate(rows, cfg, total_bucket_count=100)
    # 只有 BTC 應通過（n_filtered_rows = 1）。
    if res.get("n_filtered_rows") != 1:
        failures.append(f"per-symbol threshold 過濾錯: n_filtered_rows={res.get('n_filtered_rows')} (應=1)")


def _check_a1_source_unavailable_draft_only(failures: list[str]) -> None:
    """A1 source unavailable 時才 draft_only(basis_panel_infra_missing)。"""
    p = a1_draft_only_packet()
    if p.get("verdict") != "draft_only":
        failures.append(f"a1 verdict 錯: {p.get('verdict')}")
    if p.get("infra_gap") is not True:
        failures.append("a1 infra_gap 應 True")
    if p.get("is_signal_failure") is not False:
        failures.append("a1 is_signal_failure 應 False（infra gap 非 signal failure）")
    if A1_BASIS_INFRA_MISSING_REASON not in (p.get("fail_reasons") or []):
        failures.append("a1 fail_reasons 缺 basis_panel_infra_missing")
    if p.get("prereq_ticket") != A1_BASIS_PREREQ_TICKET:
        failures.append(f"a1 prereq_ticket 錯: {p.get('prereq_ticket')}")
    if p.get("path") != "stub_draft_only_no_cohort":
        failures.append(f"a1 path 應標明無 cohort: {p.get('path')}")


def _check_a1_functional_packet_includes_funding_carry(failures: list[str]) -> None:
    """A1 functional path：不再 stale stub；net_bps 必包含 funding carry。"""
    rows = _build_a1_panel(n_days=5)
    p = a1_candidate_packet(rows, k_prior=10, k_prior_source="manual")
    if p.get("alpha_source_id") != A1_ALPHA_SOURCE_ID:
        failures.append(f"a1 alpha_source_id 錯: {p.get('alpha_source_id')}")
    if p.get("path") != "dedicated_a1_funding_short_with_funding_carry":
        failures.append(f"a1 path 不應是 stub: {p.get('path')}")
    if p.get("infra_gap") is not False:
        failures.append("a1 functional path infra_gap 應 False")
    if A1_BASIS_INFRA_MISSING_REASON in (p.get("fail_reasons") or []):
        failures.append("a1 functional path 不應再輸出 basis_panel_infra_missing")
    stats = p.get("stats") or {}
    if not isinstance(stats, dict) or int(stats.get("n") or 0) <= 0:
        failures.append("a1 functional path 應選出合成 signals")
    gate = p.get("gate_diagnostics") or {}
    if not isinstance(gate, dict) or int(gate.get("selected_signals") or 0) <= 0:
        failures.append("a1 gate_diagnostics.selected_signals 應 >0")
    if not isinstance(gate, dict) or float(gate.get("edge_break_even_funding_rate_bps") or 0.0) <= 0.0:
        failures.append("a1 gate_diagnostics 應揭露 edge break-even funding bps")
    # 合成 row price_gross=-10, funding_carry=40, cost=22 → net=+8；
    # 若漏 funding carry，會是 -32。這鎖住核心回歸。
    avg_net = stats.get("avg_net_bps") if isinstance(stats, dict) else None
    if avg_net is None or float(avg_net) <= 0:
        failures.append(f"a1 net 應因 funding carry 為正，got {avg_net}")


def _check_full_packet_and_forbidden_output(failures: list[str]) -> None:
    """整 packet 跑通 + AMD §3.2 forbidden-output JSON 0 hit。"""
    panel = _build_a2_panel(n_days=6, per_day=4, fwd_bps=40.0,
                            btc_notional=600_000.0, eth_notional=400_000.0)
    a1_rows = _build_a1_panel(n_days=5)
    cfg = A2CandidateConfig()
    packet = run_candidates(
        panel,
        a2_total_bucket_count=1478,
        window_days=14,
        a1_feature_rows=a1_rows,
        a1_k_prior=10,
        a1_k_prior_source="manual",
        a2_cfg=cfg,
    )
    # 結構。
    if packet.get("runner_version") != "candidate_stage0r.v2":
        failures.append("runner_version 錯")
    if "A1_funding_short_v2" not in packet.get("candidates", {}):
        failures.append("packet 缺 A1 candidate")
    if "A2_liquidation_cascade_fade" not in packet.get("candidates", {}):
        failures.append("packet 缺 A2 candidate")
    if "stage0_ready" not in packet:
        failures.append("packet 缺 stage0_ready")
    # governance attest 宣告。
    ga = packet.get("governance_attest") or {}
    if ga.get("forbidden_output_present") is not False:
        failures.append("governance_attest.forbidden_output_present 應 False")
    if ga.get("no_toml_mutation") is not True:
        failures.append("governance_attest.no_toml_mutation 應 True")
    if any(t.get("ticket") == A1_BASIS_PREREQ_TICKET for t in packet.get("prereq_tickets", [])):
        failures.append("A1 functional source 可用時不應輸出 P2-BASIS-PANEL-INFRA prereq ticket")
    # forbidden-output：整 JSON 0 hit（排除 governance_attest 自我宣告欄位的合法 token）。
    blob = json.dumps(packet, ensure_ascii=False)
    # governance_attest 欄位名含 no_stage1_pass/no_auto_promote 等是合法宣告，
    # 用 value-level 檢查：forbidden token 不得作為 emit 值出現。
    # 簡化：移除 governance_attest 區塊後再 grep（該區塊只含布林宣告）。
    packet_wo_attest = dict(packet)
    packet_wo_attest.pop("governance_attest", None)
    blob2 = json.dumps(packet_wo_attest, ensure_ascii=False)
    for tok in _FORBIDDEN_TOKENS:
        if tok in blob2:
            failures.append(f"AMD §3.2 forbidden token 出現於 packet: {tok!r}")
    # eligible_for_demo_canary 必存在（唯一允許的 emit）。
    a2 = packet["candidates"]["A2_liquidation_cascade_fade"]
    if "eligible_for_demo_canary" not in a2:
        failures.append("a2 缺 eligible_for_demo_canary（唯一允許 emit）")


def _check_sample_insufficient_observe_more(failures: list[str]) -> None:
    """少樣本 → observe_more（sample insufficient，非 reject）。"""
    # 1 day × 2 rows → days=1 < 4 + n_eff 極低。
    panel = _build_a2_panel(n_days=1, per_day=2, fwd_bps=40.0,
                            btc_notional=600_000.0, eth_notional=400_000.0)
    cfg = A2CandidateConfig()
    packet = run_candidates(
        panel,
        a2_total_bucket_count=50,
        window_days=14,
        a1_feature_rows=[],
        a2_cfg=cfg,
    )
    a2 = packet["candidates"]["A2_liquidation_cascade_fade"]
    if a2.get("verdict") != "observe_more":
        failures.append(f"少樣本應 observe_more, got {a2.get('verdict')}")
    if a2.get("eligible_for_demo_canary") is not False:
        failures.append("少樣本 eligible 應 False")
    ss = a2.get("sample_sufficiency") or {}
    if ss.get("classification") not in ("sample_insufficient",):
        failures.append(f"少樣本 classification 應 sample_insufficient, got {ss.get('classification')}")
    # 整體 verdict 也應 observe_more（A2 sample 不足；A1 空 rows 不阻）。
    if packet.get("verdict") != "observe_more":
        failures.append(f"整體 verdict 應 observe_more, got {packet.get('verdict')}")


def _check_sample_sufficiency_classify(failures: list[str]) -> None:
    """_classify_sample_sufficiency 三態邏輯。"""
    # 樣本不足。
    s1 = _classify_sample_sufficiency(n_eff=10, days=2, avg_net_bps=50.0, bootstrap_60m_lower=5.0)
    if s1["classification"] != "sample_insufficient":
        failures.append(f"n_eff低應 sample_insufficient, got {s1['classification']}")
    # 樣本足 + 負 net → signal_failure。
    s2 = _classify_sample_sufficiency(n_eff=400, days=10, avg_net_bps=-5.0, bootstrap_60m_lower=-2.0)
    if s2["classification"] != "signal_failure":
        failures.append(f"足樣本負net應 signal_failure, got {s2['classification']}")
    # 樣本足 + 正 → sufficient。
    s3 = _classify_sample_sufficiency(n_eff=400, days=10, avg_net_bps=50.0, bootstrap_60m_lower=5.0)
    if s3["classification"] != "sufficient":
        failures.append(f"足樣本正net應 sufficient, got {s3['classification']}")


def _check_time_block_cscv(failures: list[str]) -> None:
    """time-block CSCV：<4 days → None observe_more；≥4 days → 非 None。"""
    # 3 days → None。
    net_3d = {"2026-05-15": [40.0, 30.0], "2026-05-16": [35.0], "2026-05-17": [20.0]}
    r3 = _time_block_cscv_pbo(net_3d)
    if r3.get("value") is not None or r3.get("reason") != "insufficient_days":
        failures.append(f"<4 days 應 pbo=None insufficient_days, got {r3}")
    # 6 days → 非 None。
    net_6d = {f"2026-05-{15+i}": [40.0, 30.0, 35.0] for i in range(6)}
    r6 = _time_block_cscv_pbo(net_6d)
    if r6.get("value") is None:
        failures.append(f"≥4 days 應 pbo 非 None, got {r6}")
    if r6.get("method") != "time_block_cscv":
        failures.append("pbo method 應 time_block_cscv")


def _check_a1_sql_exists_after_basis_land(failures: list[str]) -> None:
    """basis_panel 已 land 後，A1 SQL 必存在，避免 stale infra stub 回歸。"""
    pkg_dir = Path(__file__).resolve().parent
    sql_dir = pkg_dir.parents[2] / "sql" / "queries"
    if not (sql_dir / "alpha_candidate_a1_funding_short_features.sql").exists():
        failures.append("alpha_candidate_a1_funding_short_features.sql 缺失；A1 會退回 stale stub")


# ──────────────────────────────────────────────────────────────────────────
# k_prior auto-query / fail-closed（QC round 2 blocker fix）
# ──────────────────────────────────────────────────────────────────────────

class _FakeCursor:
    """合成 psycopg2 cursor：依預設腳本回 fetchone 結果（不接 PG）。

    fetchone_script：依序回每次 fetchone 的 row（to_regclass 存在性 → count）。
    """

    def __init__(self, fetchone_script: list[Any]):
        self._script = list(fetchone_script)
        self._i = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *_a, **_k):
        return None

    def fetchone(self):
        row = self._script[self._i]
        self._i += 1
        return row


class _FakeConn:
    def __init__(self, fetchone_script: list[Any]):
        self._script = fetchone_script

    def cursor(self):
        return _FakeCursor(self._script)


def _check_k_prior_auto_query_present(failures: list[str]) -> None:
    """ledger 存在 → fetch_k_prior 回真實 count + available=True（非 silent 0 default）。"""
    # to_regclass 回 (True,) → count(DISTINCT candidate_key) 回 (37,)。
    conn = _FakeConn([(True,), (37,)])
    k, meta = fetch_k_prior(conn, mode="strict-liquidation")
    if k != 37:
        failures.append(f"k_prior auto-query 應回 ledger count 37, got {k}")
    if meta.get("available") is not True:
        failures.append("ledger 存在時 meta.available 應 True")
    if meta.get("source") != "learning.strategy_trial_ledger":
        failures.append(f"k_prior_meta.source 錯: {meta.get('source')}")
    if meta.get("mode") != "strict-liquidation":
        failures.append(f"k_prior_meta.mode 錯: {meta.get('mode')}")


def _check_k_prior_fail_closed_unavailable(failures: list[str]) -> None:
    """ledger 表不存在 → available=False（caller 不可 silent 用 0 當權威 prior）。"""
    # to_regclass 回 (False,) → 表不存在。
    conn = _FakeConn([(False,)])
    k, meta = fetch_k_prior(conn, mode="strict-liquidation")
    # k=0 是佔位，但 meta.available=False 是 fail-closed 信號（非權威 prior）。
    if meta.get("available") is not False:
        failures.append("ledger 缺時 meta.available 應 False（fail-closed 信號）")
    if k != 0:
        failures.append(f"ledger 缺時 k 佔位應 0, got {k}")


def _check_k_prior_unavailable_downgrades_verdict(failures: list[str]) -> None:
    """fail-closed：k_prior_source=unavailable → stage0_ready 降 observe_more（非 silent PASS）。

    這是 QC round 2 blocker 核心：ledger 缺時 over-PASS 風險必須被擋。
    """
    # 合成一個「假裝 stage0_ready」的 packet（直接構造，不需真跑 DSR）。
    packet: dict[str, Any] = {
        "verdict": "stage0_ready",
        "stage0_ready": True,
        "candidates": {
            "A2_liquidation_cascade_fade": {
                "verdict": "stage0_ready",
                "eligible_for_demo_canary": True,
                "stage0_ready_candidate": True,
                "fail_reasons": [],
            }
        },
    }
    meta = {"mode": "strict-liquidation", "source": "learning.strategy_trial_ledger",
            "available": False, "where": None}
    _apply_k_prior_to_packet(
        packet, k_prior=0, k_prior_source="unavailable", k_prior_meta=meta,
        mode="strict-liquidation",
    )
    # provenance 寫入。
    if packet.get("k_prior_source") != "unavailable":
        failures.append(f"k_prior_source 應 unavailable, got {packet.get('k_prior_source')}")
    # 整體 verdict 降保守。
    if packet.get("verdict") != "observe_more":
        failures.append(f"unavailable 應降 observe_more, got {packet.get('verdict')}")
    if packet.get("stage0_ready") is not False:
        failures.append("unavailable 時 packet.stage0_ready 應 False")
    a2 = packet["candidates"]["A2_liquidation_cascade_fade"]
    if a2.get("verdict") != "observe_more":
        failures.append(f"unavailable 時 A2 verdict 應 observe_more, got {a2.get('verdict')}")
    if a2.get("eligible_for_demo_canary") is not False:
        failures.append("unavailable 時 A2 eligible 應 False（fail-closed）")
    if "k_prior_unavailable_conservative_downgrade" not in (a2.get("fail_reasons") or []):
        failures.append("unavailable 時 A2 fail_reasons 缺 downgrade 標記")


def _check_k_prior_manual_and_pbo_semantics(failures: list[str]) -> None:
    """顯式 manual k_prior 不降級 + pbo_semantics key 必存在。"""
    packet: dict[str, Any] = {
        "verdict": "stage0_ready",
        "stage0_ready": True,
        "candidates": {
            "A2_liquidation_cascade_fade": {
                "verdict": "stage0_ready",
                "eligible_for_demo_canary": True,
                "stage0_ready_candidate": True,
                "fail_reasons": [],
            }
        },
    }
    meta = {"mode": "manual", "source": "--k-prior", "available": True, "where": None}
    _apply_k_prior_to_packet(
        packet, k_prior=12, k_prior_source="manual", k_prior_meta=meta, mode="strict-liquidation",
    )
    # manual override：不降級。
    if packet.get("verdict") != "stage0_ready":
        failures.append(f"manual k_prior 不應降級, got {packet.get('verdict')}")
    if packet.get("k_prior") != 12:
        failures.append(f"packet.k_prior 應 12, got {packet.get('k_prior')}")
    if packet.get("k_prior_source") != "manual":
        failures.append("manual 時 k_prior_source 應 manual")
    # pbo_semantics key（QC non-blocking note）。
    if packet.get("pbo_semantics") != "day_block_generalization_proxy_not_bailey_cscv":
        failures.append(f"pbo_semantics key 錯或缺: {packet.get('pbo_semantics')}")


def main(argv: list[str] | None = None) -> int:
    failures: list[str] = []
    _check_a2_packet_structure(failures)
    _check_k_total_override(failures)
    _check_per_symbol_threshold_filter(failures)
    _check_a1_source_unavailable_draft_only(failures)
    _check_a1_functional_packet_includes_funding_carry(failures)
    _check_full_packet_and_forbidden_output(failures)
    _check_sample_insufficient_observe_more(failures)
    _check_sample_sufficiency_classify(failures)
    _check_time_block_cscv(failures)
    _check_a1_sql_exists_after_basis_land(failures)
    _check_k_prior_auto_query_present(failures)
    _check_k_prior_fail_closed_unavailable(failures)
    _check_k_prior_unavailable_downgrades_verdict(failures)
    _check_k_prior_manual_and_pbo_semantics(failures)

    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("PASS alpha_candidate_stage0r runner smoke")
    print(f"A2_ALPHA_SOURCE_ID={A2_ALPHA_SOURCE_ID}")
    print(f"A2_K_NEW_CANDIDATE={A2_K_NEW_CANDIDATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
