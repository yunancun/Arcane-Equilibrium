"""P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up — resting maker exposure 哨兵。

MODULE_NOTE:
  ``[68]`` portfolio_resting_exposure_lineage 監測 paper_state resting maker
  orders 的 effective notional exposure，配對 P1-PORTFOLIO-RESTING-EXPOSURE-1
  Rust IMPL（commit ``9980448a`` 將 ``resting_limit_orders`` 納入
  ``compute_effective_long_short_notional`` SoT helper）。

  哨兵目的（per A3 ``2026-05-16--p1_portfolio_resting_exposure_a3_adversarial_review``
  WARN-1 + E2 LOW-1 + PA F-FA-2 verify §8）：
    監控 effective（filled + resting）vs filled-only leverage chain semantic
    drift magnitude。當 close-side resting 大量未 fill 時 leverage 隨
    effective 降低，可能放行更多 entry — 不是 regression（合理保守反映），
    但需要 Stage 1 demo 啟動前先看到分歧的真實 magnitude。

  資料源（純 PG + filesystem，無 IPC，與 sibling check ``[56]/[57]/[58]/[67]``
  pattern 對齊）：
    1. ``trading.orders`` + ``trading.order_state_changes`` — derive
       latest state per ``order_id`` filter ``to_status='Working'`` →
       per (engine_mode, symbol, side) 加總 resting notional
       （``qty × price``）。
    2. ``pipeline_snapshot_{paper,demo,live}.json`` — read
       ``paper_state.positions[*]`` 計算每 engine 的 filled-long /
       filled-short notional（``qty × entry_price``）+ ``balance``。
    3. ``settings/risk_control_rules/risk_config_{engine}.toml`` —
       讀 ``correlated_exposure_max_pct`` 作 cap reference。

  Verdict matrix（per PM dispatch §6 acceptance）：
    PASS：所有 engine 的 long/short/per-symbol notional < cap × 80%
          AND divergence_pct < 50%
    WARN：任一 engine notional ≥ cap × 80%（但 < cap）
          OR divergence_pct ∈ [50%, 100%)
          OR per-symbol resting/filled ratio ≥ 80%
    FAIL：任一 engine notional ≥ cap
          OR divergence_pct ≥ 100%
          OR per-symbol resting notional > 1.5 × filled
          OR per-symbol violation（resting only without filled position ≥ cap）

  Pre-deploy 行為：
    - ``trading.orders`` / ``trading.order_state_changes`` 缺 → PASS_SKIP
    - 任一 ``pipeline_snapshot_*.json`` 缺 → 對應 engine 跳過（其他 engine 仍跑）
    - 無 Working orders → PASS（lineage 沒分歧，是穩態）

  Opt-in env：
    - ``OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1``：WARN 升 FAIL（Stage 1
      demo 啟動後切嚴）
    - ``OPENCLAW_PORTFOLIO_RESTING_LOOKBACK_HOURS=N``：Working orders ts 視窗
      （default 24h，避免拉太久增量 false-positive）。

  Sister check：
    - ``[56] live_pipeline_active``：純檔案系統，驗 live slot/snapshot 新鮮度
    - ``[57] btc_lead_lag_panel_health``：W2 panel 4 條件
    - ``[58] graduated_canary_stage_invariant``：W-AUDIT-9 T4 canary stage 不變式
    - ``[67] feature_baseline_readiness``：W-AUDIT-4b feature baseline

  ID 註：PA spec / TODO row / A3 / E2 report 標 ``[58]`` 但 runner 真實
  ``[58]`` 已被 W-AUDIT-9 T4 占用（``check_58_graduated_canary_stage_invariant``）。
  本 check 取下一個自由 slot ``[68]``，name 保留 ``portfolio_resting_exposure_lineage``。
  若 PM 要求改 sub-suffix（如 ``[58b]``）只需改 ID 不需動 logic。

  對應 cron：``helper_scripts/db/passive_wait_healthcheck_cron.sh``
  （CLAUDE.md §七「被動等待 TODO 必附 healthcheck」強制配對）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ============================================================
# §1 常數定義
# ============================================================

# Engine modes：``trading.orders.engine_mode`` 可能值 + 對應 snapshot 檔名
# paper/demo/live 各自有 ``pipeline_snapshot_{name}.json``；live_demo 共用 live snapshot
# (LiveDemo 是 Live 管線走 demo endpoint，per CLAUDE.md §四 hardcap)。
ENGINE_MODES: tuple[str, ...] = ("paper", "demo", "live", "live_demo")

# Engine → snapshot 檔名映射（live + live_demo 共用 live snapshot）
ENGINE_TO_SNAPSHOT: dict[str, str] = {
    "paper": "pipeline_snapshot_paper.json",
    "demo": "pipeline_snapshot_demo.json",
    "live": "pipeline_snapshot_live.json",
    "live_demo": "pipeline_snapshot_live.json",
}

# Engine → TOML 檔名（讀 ``correlated_exposure_max_pct``）
# paper/demo/live 各自有獨立 TOML（per feedback_env_config_independence）；
# live_demo 對齊 demo TOML（LiveDemo 用 demo endpoint，policy 由 demo TOML 控）
ENGINE_TO_RISK_TOML: dict[str, str] = {
    "paper": "risk_config_paper.toml",
    "demo": "risk_config_demo.toml",
    "live": "risk_config_live.toml",
    "live_demo": "risk_config_demo.toml",
}

# Working orders 視窗（避免拉太久增量 false-positive；cancel 沒及時寫 state_changes）
DEFAULT_LOOKBACK_HOURS: int = 24

# 閾值 — PM dispatch §6 acceptance criteria
# PASS：< cap × 80%；WARN：≥ cap × 80%；FAIL：≥ cap × 100%
# divergence_pct = total_resting / max(total_filled, 1.0)
CAP_USAGE_WARN_RATIO: float = 0.80
CAP_USAGE_FAIL_RATIO: float = 1.00

# Divergence thresholds（A3 WARN-1 monitoring magnitude）
DIVERGENCE_WARN_PCT: float = 0.50  # 50% — resting is half of filled
DIVERGENCE_FAIL_PCT: float = 1.00  # 100% — resting matches/exceeds filled

# Per-symbol resting / filled ratio（PM dispatch acceptance）
PER_SYMBOL_WARN_RATIO: float = 0.80   # WARN：resting ≥ 80% filled
PER_SYMBOL_FAIL_RATIO: float = 1.50   # FAIL：resting > 1.5× filled

# Fallback cap pct（TOML 缺時用，仍保健康檢查可跑）；對齊 demo TOML default
FALLBACK_CORRELATED_CAP_PCT: float = 65.0


# ============================================================
# §2 helper
# ============================================================


def _enabled(name: str, default: str = "0") -> bool:
    """讀取 env flag（"1" 才視為啟用），其他值（含未設）回 False。"""
    return os.getenv(name, default).strip() == "1"


def _status_for(required: bool, base: str) -> str:
    """REQUIRED env 設定時把 WARN 升 FAIL；否則維持原 verdict。"""
    if base == "WARN" and required:
        return "FAIL"
    return base


def _lookback_hours() -> int:
    """讀 env override，否則取 default 24h；無效值 fallback default。"""
    raw = os.getenv("OPENCLAW_PORTFOLIO_RESTING_LOOKBACK_HOURS", "").strip()
    if not raw:
        return DEFAULT_LOOKBACK_HOURS
    try:
        v = int(raw)
        return v if v > 0 else DEFAULT_LOOKBACK_HOURS
    except ValueError:
        return DEFAULT_LOOKBACK_HOURS


def _data_dir() -> Path:
    """取 ``OPENCLAW_DATA_DIR``，默認 ``/tmp/openclaw``（與 Rust persistence.rs 對齊）。"""
    return Path(os.getenv("OPENCLAW_DATA_DIR", "/tmp/openclaw"))


def _base_dir() -> Path:
    """取 ``OPENCLAW_BASE_DIR``，默認 ``$HOME/BybitOpenClaw/srv``（與 Linux runtime 對齊）。"""
    env = os.getenv("OPENCLAW_BASE_DIR")
    if env:
        return Path(env)
    home = os.getenv("HOME") or os.getenv("USERPROFILE") or "/tmp"
    return Path(home) / "BybitOpenClaw" / "srv"


def _read_correlated_cap_pct(engine: str) -> tuple[float, str]:
    """讀 ``risk_config_{engine}.toml`` 的 ``[exposure]/correlated_exposure_max_pct``。

    Returns (cap_pct, diagnostic)。TOML 缺 / parse 失敗 / 欄位缺 → fallback default
    + diagnostic 紀錄；不 raise（fail-soft 不阻 healthcheck）。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        except ImportError:
            return (FALLBACK_CORRELATED_CAP_PCT, "tomllib/tomli unavailable")

    toml_name = ENGINE_TO_RISK_TOML.get(engine)
    if not toml_name:
        return (FALLBACK_CORRELATED_CAP_PCT, f"engine={engine} 無 TOML 映射")

    toml_path = _base_dir() / "settings" / "risk_control_rules" / toml_name
    if not toml_path.exists():
        return (FALLBACK_CORRELATED_CAP_PCT, f"{toml_name} 不存在 fallback={FALLBACK_CORRELATED_CAP_PCT}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:  # noqa: BLE001 - fail-soft：TOML parse 失敗回 default
        return (FALLBACK_CORRELATED_CAP_PCT, f"{toml_name} parse 失敗: {type(e).__name__}: {e}")

    # 結構：[exposure] correlated_exposure_max_pct = 65.0
    # 或頂層 correlated_exposure_max_pct = 65.0（risk_config*.toml 各環境結構可能不同）
    cap = None
    if isinstance(data, dict):
        cap = data.get("correlated_exposure_max_pct")
        if cap is None:
            section = data.get("exposure") or data.get("risk")
            if isinstance(section, dict):
                cap = section.get("correlated_exposure_max_pct")

    if not isinstance(cap, (int, float)) or cap <= 0:
        return (FALLBACK_CORRELATED_CAP_PCT, f"{toml_name} correlated_exposure_max_pct 缺/非正 fallback")

    return (float(cap), "ok")


def _read_snapshot(engine: str) -> tuple[dict[str, Any] | None, str]:
    """讀 ``pipeline_snapshot_{engine}.json`` 並 return parsed dict + diagnostic。

    Returns (snap_dict, diagnostic)；snap 不存 / parse 失敗 → (None, reason)
    （fail-soft）。
    """
    name = ENGINE_TO_SNAPSHOT.get(engine)
    if not name:
        return (None, f"engine={engine} 無 snapshot 映射")

    path = _data_dir() / name
    if not path.exists():
        return (None, f"{name} 不存在 (engine 未 spawn 或 path 漂移)")

    try:
        return (json.loads(path.read_text(encoding="utf-8")), "ok")
    except Exception as e:  # noqa: BLE001 - fail-soft：parse 失敗只跳該 engine
        return (None, f"{name} parse 失敗: {type(e).__name__}: {e}")


def _filled_notional_from_snapshot(snap: dict[str, Any]) -> tuple[dict[str, dict[str, float]], float]:
    """從 snapshot 抽 paper_state.positions[*] 計算 per-symbol filled notional + balance。

    Returns (
      per_symbol = {"BTCUSDT": {"long": 250.0, "short": 0.0}, ...},
      balance = 10000.0
    )

    snapshot.paper_state.positions 是 ``PositionSnapshot`` list（per
    Rust ``paper_state/snapshots.rs:20``）。每 row 含 ``symbol`` / ``is_long`` /
    ``qty`` / ``entry_price``。filled notional 用 ``qty × entry_price``
    （與 Rust ``intent_processor::compute_effective_long_short_notional``
    SoT helper line 805-810 對齊）。
    """
    per_symbol: dict[str, dict[str, float]] = {}
    paper_state = snap.get("paper_state", {})
    if not isinstance(paper_state, dict):
        return (per_symbol, 0.0)

    balance = float(paper_state.get("balance", 0.0) or 0.0)
    positions = paper_state.get("positions", [])
    if not isinstance(positions, list):
        return (per_symbol, balance)

    for raw in positions:
        if not isinstance(raw, dict):
            continue
        # PositionSnapshot 用 #[serde(flatten)] 把 PaperPosition 欄位平鋪
        symbol = raw.get("symbol")
        is_long = raw.get("is_long")
        qty = raw.get("qty")
        entry_price = raw.get("entry_price")
        if not isinstance(symbol, str) or not isinstance(is_long, bool):
            continue
        try:
            qty_f = float(qty or 0.0)
            entry_f = float(entry_price or 0.0)
        except (TypeError, ValueError):
            continue
        # 過濾非 finite / 非正（與 Rust helper 一致：order.qty > 0 && limit_price > 0）
        if qty_f <= 0.0 or entry_f <= 0.0 or qty_f != qty_f or entry_f != entry_f:
            continue
        notional = qty_f * entry_f
        bucket = per_symbol.setdefault(symbol, {"long": 0.0, "short": 0.0})
        if is_long:
            bucket["long"] += notional
        else:
            bucket["short"] += notional

    return (per_symbol, balance)


def _resting_notional_from_pg(
    cur,
    engine: str,
    lookback_hours: int,
) -> tuple[dict[str, dict[str, float]], int, str]:
    """從 ``trading.orders`` + ``trading.order_state_changes`` 抽 currently
    Working orders → per (engine_mode, symbol, side) 加總 notional。

    Returns (per_symbol, working_count, diagnostic)：
      per_symbol = {"BTCUSDT": {"long": 120.0, "short": 0.0}, ...}
      working_count = 累計 row 數（debugging 用）
      diagnostic = "ok" / fail-soft reason

    SQL 設計：
      1. 從 ``order_state_changes`` 取每 ``order_id`` 最新 ``to_status``
      2. JOIN ``orders`` 拿 symbol / side / qty / price / engine_mode
      3. 過濾 ``to_status='Working'`` AND ``engine_mode=%s``
      4. notional = qty × price（price 缺時 fallback 0，這 row 不計）
      5. lookback ts 過濾用 ``orders.ts``（避免拉 30d 全表）
    """
    # 表存在性 + 0 row 防禦
    try:
        cur.execute(
            "SELECT to_regclass('trading.orders') IS NOT NULL, "
            "       to_regclass('trading.order_state_changes') IS NOT NULL"
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ({}, 0, f"trading.orders/order_state_changes 存在性查詢失敗: {type(exc).__name__}")

    if not row or not row[0] or not row[1]:
        return ({}, 0, "trading.orders 或 order_state_changes 缺（pre-V003 deploy）")

    try:
        # latest_state per order_id via DISTINCT ON；JOIN orders 拿 symbol/side/qty/price
        # 過濾 engine_mode + Working + lookback。price 缺 fallback 0（不會加 notional）。
        cur.execute(
            """
            WITH latest_state AS (
                SELECT DISTINCT ON (order_id)
                    order_id,
                    to_status
                FROM trading.order_state_changes
                WHERE ts > NOW() - (%s::text || ' hours')::interval
                ORDER BY order_id, ts DESC
            )
            SELECT
                o.symbol,
                o.side,
                SUM(o.qty * COALESCE(o.price, 0.0))::FLOAT AS notional_sum,
                COUNT(*)::INT AS row_count
            FROM trading.orders o
            JOIN latest_state ls ON o.order_id = ls.order_id
            WHERE ls.to_status = 'Working'
              AND o.engine_mode = %s
              AND o.ts > NOW() - (%s::text || ' hours')::interval
            GROUP BY o.symbol, o.side
            """,
            (lookback_hours, engine, lookback_hours),
        )
        rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ({}, 0, f"Working orders aggregate 失敗: {type(exc).__name__}: {exc}")

    per_symbol: dict[str, dict[str, float]] = {}
    total_count = 0
    for r in rows:
        symbol, side, notional, count = r[0], r[1], r[2], r[3]
        if not isinstance(symbol, str) or not isinstance(side, str):
            continue
        notional_f = float(notional or 0.0)
        if notional_f <= 0.0 or notional_f != notional_f:
            continue
        bucket = per_symbol.setdefault(symbol, {"long": 0.0, "short": 0.0})
        # Bybit side 對應：Buy=long，Sell=short（與 trading_writer.rs:759 對齊）
        if side == "Buy":
            bucket["long"] += notional_f
        elif side == "Sell":
            bucket["short"] += notional_f
        # 其他 side（例外/未知）忽略，不污染 bucket
        total_count += int(count or 0)

    return (per_symbol, total_count, "ok")


# ============================================================
# §3 main check
# ============================================================


def check_68_portfolio_resting_exposure(cur) -> tuple[str, str]:
    """``[68]`` portfolio_resting_exposure_lineage — resting maker exposure 哨兵。

    Pure SELECT inside cursor block + filesystem read（snapshot JSON + TOML）；
    defensive rollback at top to keep cursor clean across sibling checks（與
    ``[55]/[57]/[58]/[67]`` 同 pattern）。

    Returns (status, detail_msg)：
      - "PASS"：所有 engine 的 long/short/per-symbol notional < cap × 80%
                AND divergence < 50%
      - "WARN"：notional ≥ cap × 80%（< cap）OR divergence ∈ [50%, 100%)
                OR per-symbol resting/filled ≥ 80%
      - "FAIL"：notional ≥ cap OR divergence ≥ 100% OR per-symbol > 1.5× filled
                OR per-symbol violation (resting only 無 filled position ≥ cap)
    """
    # Defensive rollback 保 cursor 在 sibling check 間乾淨
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 - defensive cleanup must not raise
        pass

    required = _enabled("OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED")
    lookback_hours = _lookback_hours()

    # ── 每 engine 跑一次（paper / demo / live / live_demo）
    # 累計分項 verdict + per-engine raw evidence
    engine_verdicts: list[str] = []
    engine_evidence: list[str] = []
    skipped_engines: list[str] = []

    for engine in ENGINE_MODES:
        # 1. 讀 snapshot → filled notional + balance
        snap, snap_diag = _read_snapshot(engine)
        if snap is None:
            # snapshot 缺 → 跳過該 engine（其他 engine 仍跑，不阻塞）
            skipped_engines.append(f"{engine}({snap_diag})")
            continue
        filled_per_symbol, balance = _filled_notional_from_snapshot(snap)

        # 2. 讀 PG → resting notional per (symbol, side)
        resting_per_symbol, working_count, resting_diag = _resting_notional_from_pg(
            cur, engine, lookback_hours
        )
        if resting_diag != "ok" and not resting_per_symbol:
            # PG 查詢失敗但 snapshot 還在 → 對該 engine WARN 帶診斷
            engine_verdicts.append("WARN")
            engine_evidence.append(f"{engine}=PG_FAIL({resting_diag})")
            continue

        # 3. 讀 TOML → correlated cap pct
        cap_pct, cap_diag = _read_correlated_cap_pct(engine)
        # balance ≤ 0 → 無法算 cap 絕對值；該 engine 仍報告 raw notional
        cap_abs = (cap_pct / 100.0) * balance if balance > 0 else 0.0

        # 4. 聚合 long/short notional（filled + resting）
        total_filled_long = sum(v.get("long", 0.0) for v in filled_per_symbol.values())
        total_filled_short = sum(v.get("short", 0.0) for v in filled_per_symbol.values())
        total_resting_long = sum(v.get("long", 0.0) for v in resting_per_symbol.values())
        total_resting_short = sum(v.get("short", 0.0) for v in resting_per_symbol.values())
        total_filled = total_filled_long + total_filled_short
        total_resting = total_resting_long + total_resting_short

        # 5. divergence_pct = resting / max(filled, 1.0)
        divergence_pct = total_resting / max(total_filled, 1.0)

        # 6. 分項 verdict（per engine）
        engine_verdict = "PASS"
        violations: list[str] = []

        # (a) Aggregate notional vs cap（每方向獨立查）
        if cap_abs > 0:
            for side_name, side_notional in (
                ("long_total", total_filled_long + total_resting_long),
                ("short_total", total_filled_short + total_resting_short),
            ):
                if side_notional >= cap_abs * CAP_USAGE_FAIL_RATIO:
                    engine_verdict = "FAIL"
                    violations.append(f"{side_name}={side_notional:.0f}≥cap={cap_abs:.0f}")
                elif side_notional >= cap_abs * CAP_USAGE_WARN_RATIO:
                    if engine_verdict == "PASS":
                        engine_verdict = "WARN"
                    violations.append(
                        f"{side_name}={side_notional:.0f}≥{CAP_USAGE_WARN_RATIO:.0%}cap"
                    )

        # (b) Divergence pct
        if divergence_pct >= DIVERGENCE_FAIL_PCT:
            engine_verdict = "FAIL"
            violations.append(f"divergence={divergence_pct:.1%}≥{DIVERGENCE_FAIL_PCT:.0%}")
        elif divergence_pct >= DIVERGENCE_WARN_PCT:
            if engine_verdict == "PASS":
                engine_verdict = "WARN"
            violations.append(f"divergence={divergence_pct:.1%}≥{DIVERGENCE_WARN_PCT:.0%}")

        # (c) Per-symbol：resting / filled ratio + resting-only no-filled cap
        # 集合：所有有 resting 或 filled 的 symbol
        all_symbols = set(filled_per_symbol.keys()) | set(resting_per_symbol.keys())
        per_symbol_warnings: list[str] = []
        per_symbol_fails: list[str] = []
        for sym in all_symbols:
            f_long = filled_per_symbol.get(sym, {}).get("long", 0.0)
            f_short = filled_per_symbol.get(sym, {}).get("short", 0.0)
            r_long = resting_per_symbol.get(sym, {}).get("long", 0.0)
            r_short = resting_per_symbol.get(sym, {}).get("short", 0.0)
            f_total = f_long + f_short
            r_total = r_long + r_short

            # resting-only (filled = 0) 且 r_total ≥ cap × 50% → FAIL
            # （symbol 無 filled 但 resting 大量，是 entry-only resting accumulating，
            #  per-symbol over-exposure 風險，FA verdict 認為這是 Stage 1 demo
            #  必看的「沒倉但下了大單」訊號）
            if f_total <= 0.0 and r_total > 0.0 and cap_abs > 0 and r_total >= cap_abs * 0.5:
                per_symbol_fails.append(f"{sym}=resting-only:{r_total:.0f}≥0.5×cap")
                continue

            # filled > 0 → 看比率
            if f_total > 0.0:
                ratio = r_total / f_total
                if ratio >= PER_SYMBOL_FAIL_RATIO:
                    per_symbol_fails.append(f"{sym}=r/f:{ratio:.1f}≥{PER_SYMBOL_FAIL_RATIO:.1f}")
                elif ratio >= PER_SYMBOL_WARN_RATIO:
                    per_symbol_warnings.append(f"{sym}=r/f:{ratio:.1f}")

        if per_symbol_fails:
            engine_verdict = "FAIL"
            violations.append(f"per_symbol_fail=[{','.join(per_symbol_fails[:3])}]")
        elif per_symbol_warnings:
            if engine_verdict == "PASS":
                engine_verdict = "WARN"
            violations.append(f"per_symbol_warn=[{','.join(per_symbol_warnings[:3])}]")

        # 7. 收口 evidence
        engine_verdicts.append(engine_verdict)
        evidence = (
            f"{engine}={engine_verdict}("
            f"bal={balance:.0f},"
            f"filled={total_filled:.0f}(L{total_filled_long:.0f}/S{total_filled_short:.0f}),"
            f"resting={total_resting:.0f}(L{total_resting_long:.0f}/S{total_resting_short:.0f}),"
            f"working_n={working_count},"
            f"divergence={divergence_pct:.1%},"
            f"cap={cap_abs:.0f}({cap_pct:.0f}%/{cap_diag})"
        )
        if violations:
            evidence += f",violations=[{';'.join(violations[:3])}]"
        evidence += ")"
        engine_evidence.append(evidence)

    # ── 全部 engine 收口
    if not engine_verdicts:
        # 全部 engine snapshot 都缺 → PASS（pre-deploy / Mac dev / engine cold）
        return (
            "PASS",
            f"[68] portfolio_resting_exposure_lineage skipped — 全部 engine "
            f"snapshot 缺 (skipped={','.join(skipped_engines)}); "
            f"lookback_hours={lookback_hours}",
        )

    # 任一 engine FAIL → 全局 FAIL；任一 WARN → 全局 _status_for(WARN)；否則 PASS
    has_fail = any(v == "FAIL" for v in engine_verdicts)
    has_warn = any(v == "WARN" for v in engine_verdicts)

    if has_fail:
        verdict = "FAIL"
    elif has_warn:
        verdict = _status_for(required, "WARN")
    else:
        verdict = "PASS"

    # 收口訊息
    skipped_msg = ""
    if skipped_engines:
        skipped_msg = f" skipped=[{','.join(skipped_engines)}]"

    if verdict == "PASS":
        return (
            "PASS",
            f"[68] portfolio resting exposure healthy "
            f"({' | '.join(engine_evidence)}) lookback={lookback_hours}h"
            f"{skipped_msg}",
        )
    if verdict == "WARN":
        return (
            "WARN",
            f"[68] portfolio resting exposure approaching limit / divergence rising "
            f"({' | '.join(engine_evidence)}) lookback={lookback_hours}h"
            f"{skipped_msg}",
        )
    return (
        "FAIL",
        f"[68] portfolio resting exposure breach / divergence critical "
        f"({' | '.join(engine_evidence)}) lookback={lookback_hours}h"
        f"{skipped_msg}",
    )
