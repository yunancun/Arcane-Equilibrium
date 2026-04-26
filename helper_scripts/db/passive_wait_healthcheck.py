#!/usr/bin/env python3
"""Passive-wait pipeline healthcheck.
被動等待管線健康檢查。

MODULE_NOTE (EN): Single-command check that 7 key runtime data pipelines
are actually producing data, versus silently failing under fail-open
error handling. Triggered by 2026-04-22 P1-19 RCA which discovered that
phys_lock / MICRO-PROFIT / label backfill pipelines had all been silently
dead for 2.5–3 days despite "passive wait" TODOs treating them as healthy.

MODULE_NOTE (中): 單命令檢查 7 個關鍵 runtime 資料管線實際有資料流入，
識破 fail-open 下的 silent failure。由 2026-04-22 P1-19 RCA 觸發 — 當時
發現 phys_lock / MICRO-PROFIT / label backfill 三條管線都 silent-dead
2.5-3 天，但 TODO 卻敘述為「被動等待中（健康）」。

Usage:
  POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... \\
    python3 helper_scripts/db/passive_wait_healthcheck.py

Exit codes:
  0 = all checks PASS (all 7 pipelines healthy)
  1 = ≥1 check FAIL (pipeline silent-dead or anomalous)
  2 = DB connection error

Checks（each prints PASS / FAIL / WARN with a one-line explanation）:
  [1]  close_fills_24h                 — baseline: close fills on demo in last 24h
  [2]  label_backfill_ratio            — learning.decision_features writes vs close_fills ratio
                                          (G6-01 [2a]: includes table-existence guard +
                                           entry_context_id JOIN ratio for fills→features linkage)
  [3]  exit_features_writer_ratio      — learning.exit_features writes vs close_fills (EXIT-FEATURES-TABLE-1)
  [4]  phys_lock_runtime               — trading.fills 'risk_close:phys_lock_*' count (TRACK-P v2)
  [5]  micro_profit_fire (RETIRED)     — legacy COST EDGE gate replaced by PHYS-LOCK in TRACK-P-V2-SWAP-1
                                          (commit 306993e, 2026-04-22). [4] phys_lock_runtime is the
                                          authoritative micro-profit-lock health signal. [5] always
                                          returns PASS w/ historical residue counts (informational).
  [6]  trailing_stop_fire              — trading.fills 'risk_close:TRAILING STOP%' count
  [7]  edge_estimates_freshness        — settings/edge_estimates.json mtime < 90min
                                          (G6-01 [7a]: includes structure validation + active
                                           runtime owner_strategy prefix coverage warning)
  [8]  shadow_exits_24h                — INFRA-PREBUILD-1 Part A; ExitConfig.shadow_enabled gate
  [9]  model_registry_freshness        — INFRA-PREBUILD-1 Part B; production-model train_date age
  [10] intents_writer_ratio            — trading.intents vs orders 24h ratio (P1-12 post-mortem 2026-04-17 outage)
  [11] counterfactual_clean_window_growth — post-P013-clean EDGE-DIAG-1 Phase 3 gate (2026-04-24)
  [12] bb_breakout_post_deadlock_fix   — bb_breakout fill rate after FIX-26-DEADLOCK-1 deploy (P1-11 (1) Phase 1)
  [13] edge_estimator_scheduler_fresh  — G6-02 new: edge_estimates.json mtime <6h + cells ≥50
                                          (tighter sibling of [7]/[7a]; G1-01/G4-04 recovery target).
  [14] exit_features_accumulation_rate — G6-02 new: weekly row growth ≥0.5× last week
                                          (EDGE-P1b ML-training accumulation passive-wait sentinel).
  [15] shadow_exit_agreement_phase2    — G6-02 new: Combine ↔ Physical 24h agreement ≥95%
                                          (EDGE-P2 Phase 2 strict quality gate; PASS when dormant).
  [16] strategist_cycle_fresh          — G3-11 new (2026-04-25 MVP): Rust StrategistScheduler
                                          last cycle completion ≤10min ago via IPC
                                          `get_strategist_cycle_metrics`. Pure liveness sentinel —
                                          catches scheduler wedged / engine restart-without-rebind /
                                          AI service down causing exponential backoff to 4h.
                                          PASS when scheduler unbound (Demo missing — by design).
  [18] disabled_strategy_inventory     — G2-06 new (2026-04-26): pure observability listing
                                          strategies with [<name>].active=false in
                                          strategy_params_demo.toml. CLAUDE.md §三 drift defense
                                          (G6-04) — ensures disabled strategies stay visible so
                                          future audits can't "forget" them. Always PASS.
  [Xa] leader_election_health          — G6-01 new: edge_estimator_scheduler flock file age +
                                          leader-PID liveness; catches stale-lock / dead-leader
                                          drift that masks scheduler silent-death (edge_estimates
                                          freshness alone misses leader-election failures).
  [Xb] pipeline_triangulation          — G6-01 new: cross-validates [1] close_fills / [2] labels /
                                          [10] intents scale ratios. Individual checks pass their
                                          local thresholds but collectively can diverge (e.g. fills
                                          healthy + labels healthy + intents 10× over — suggests a
                                          duplicate-intent writer bug that neither [1] nor [10]
                                          individually catches). Covers QA §2.2 #4 blind spot
                                          "12 檢查彼此獨立，無 fills/labels/intents 三角形驗證".

Rule of thumb: close_fills_24h ≥ 10 且 labels 1:1 ratio ≥ 0.8 且 exit_features
1:1 ratio ≥ 0.8 且 ≥1 risk-layer exit mechanism (#4/5/6) fire ≥ 1 time.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---- connection ----

def _get_conn():
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


# ---- single-query helpers ----

def _scalar(cur, sql: str) -> int:
    cur.execute(sql)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ---- individual checks ----

def check_close_fills_24h(cur) -> tuple[str, str, int]:
    """[1] Baseline: demo close_fills in last 24h. All other ratios built on this."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' AND realized_pnl != 0"
    )
    if n == 0:
        return ("FAIL", f"demo 24h close_fills = 0 — P1-10 fee drag 極度壓制 or engine dead", n)
    if n < 5:
        return ("WARN", f"demo 24h close_fills = {n} — extremely low sample, ratios unreliable", n)
    return ("PASS", f"demo 24h close_fills = {n}", n)


def check_label_backfill_ratio(cur, close_fills: int) -> tuple[str, str]:
    """[2] learning.decision_features labels vs close_fills (target ratio ≥ 0.5).

    G6-01 [2a] (2026-04-24): upgraded to a 3-layer guard against silent-dead
    label backfill that the original ratio-only check could not catch:

    1. **Table-existence guard** — `learning.decision_features` is a hypertable
       provisioned by V019. If V019 silent-noop'd (V023 postmortem pattern),
       the table is absent and the original `SELECT COUNT(*) FROM ...` would
       raise `UndefinedTable` → caller wrapped exception → ambiguous WARN.
       Now we explicitly check `to_regclass(...) IS NOT NULL` first and FAIL
       with a clear "V019 not applied" message.

    2. **Original ratio guard** (preserved): label rows / close_fills ratio
       triage; <0.3 FAIL, <0.7 WARN, ≥0.7 PASS.

    3. **JOIN-ratio guard** — the QA audit (2026-04-24 §2.2 #1) flagged that a
       healthy total ratio still hides broken `entry_context_id` linkage:
       fills can land with `entry_context_id` populated but the matching
       `decision_features` row may never appear, breaking downstream
       counterfactual / training joins. We compute the actual JOIN ratio
       between `trading.fills.entry_context_id` (closes only) and
       `learning.decision_features.context_id` for the same 24h window;
       <0.3 FAIL, <0.7 WARN annotation appended to the main verdict. JOIN
       failure does not downgrade an existing PASS to FAIL silently — it
       upgrades the message to WARN with the linkage ratio shown.

    [2] learning.decision_features 標籤 vs close_fills 比率（目標 ≥0.5）。
    G6-01 [2a]（2026-04-24）三層守衛：
      1. 表存在性：V019 silent-noop（V023 postmortem 模式）→ 直接 FAIL，不
         讓原 try/except 把 UndefinedTable 吞成 ambiguous WARN。
      2. 原比率守衛：總標籤 / close_fills，<0.3 FAIL / <0.7 WARN / ≥0.7 PASS。
      3. JOIN linkage 守衛：實算 fills.entry_context_id ↔ features.context_id
         的 JOIN 比率，<0.3 FAIL（linkage 斷裂指紋）/ <0.7 WARN annotated。
         JOIN 失敗不會悄悄把總比率 PASS 降為 FAIL；linkage 比率附加到訊息上。
    """
    # [2a] guard 1: table-existence check — V019 provisioned `learning.decision_features`.
    # Without this, an absent hypertable raises UndefinedTable and the original
    # exception path returned ambiguous WARN — masking V023-style silent-noop
    # migration failures (`migrations` ledger says "applied" but DDL skipped).
    # [2a] guard 1：表存在性 — V019 建 learning.decision_features hypertable。
    # 若缺，原 SELECT 會 UndefinedTable，舊版回 ambiguous WARN，遮蔽 V023-postmortem
    # 模式（migrations ledger 說「已套用」但 DDL 跳過）的 silent-noop migration 失敗。
    try:
        cur.execute("SELECT to_regclass('learning.decision_features') IS NOT NULL")
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"label table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.decision_features missing — V019 not applied (audit_migrations.py)")

    n = _scalar(cur,
        "SELECT COUNT(*) FROM learning.decision_features "
        "WHERE label_filled_at > now() - interval '24 hours' "
        "AND label_net_edge_bps IS NOT NULL "
        "AND engine_mode = 'demo'"
    )
    if close_fills == 0:
        return ("WARN", f"no close_fills baseline, labels={n} unscoreable")
    ratio = n / close_fills if close_fills else 0.0

    # [2a] guard 3: JOIN linkage between fills.entry_context_id and
    # decision_features.context_id (counterfactual / training joins
    # silently break when this drops). Best-effort — failures don't
    # downgrade overall verdict, just annotate.
    # [2a] guard 3：fills.entry_context_id ↔ features.context_id JOIN 比率
    # （斷裂時 counterfactual / training join 全壞）。Best-effort — 失敗不
    # 降級總結論，僅附加註解。
    join_annot = ""
    try:
        cur.execute("""
            WITH closes AS (
                SELECT entry_context_id
                FROM trading.fills
                WHERE ts > now() - interval '24 hours'
                  AND engine_mode = 'demo'
                  AND realized_pnl != 0
                  AND entry_context_id IS NOT NULL
            ),
            joined AS (
                SELECT c.entry_context_id
                FROM closes c
                INNER JOIN learning.decision_features d
                  ON d.context_id = c.entry_context_id
            )
            SELECT
                (SELECT COUNT(*) FROM closes)::int AS n_closes_with_ctx,
                (SELECT COUNT(*) FROM joined)::int AS n_joined
        """)
        n_ctx, n_join = cur.fetchone()
        if n_ctx and n_ctx > 0:
            join_ratio = n_join / n_ctx
            if join_ratio < 0.3:
                join_annot = f", JOIN_LINKAGE_LOW {n_join}/{n_ctx} ({join_ratio:.0%})"
            elif join_ratio < 0.7:
                join_annot = f", join_linkage {n_join}/{n_ctx} ({join_ratio:.0%}) partial"
            else:
                join_annot = f", join_linkage {join_ratio:.0%}"
    except Exception as e:
        # JOIN probe failed (e.g. legacy schema missing entry_context_id col);
        # don't fail the check — just note the gap.
        # JOIN 探測失敗（如舊 schema 缺欄）— 不讓整體 check 紅，僅註明。
        join_annot = f", join_probe_unavailable: {type(e).__name__}"

    base = f"labels_24h={n} vs close_fills={close_fills} (ratio {ratio:.2f}){join_annot}"
    if ratio < 0.3:
        return ("FAIL", base + " — backfill stalled")
    if ratio < 0.7:
        return ("WARN", base + " — partial backfill")
    # If ratio passes but JOIN linkage cratered, downgrade to WARN — the
    # downstream join consumers care more about linkage than total volume.
    # 比率 PASS 但 JOIN 斷裂時降為 WARN — 下游 join consumer 關注 linkage 勝過總量。
    if "JOIN_LINKAGE_LOW" in join_annot:
        return ("WARN", base + " — JOIN linkage low (counterfactual / training joins broken)")
    return ("PASS", base)


def check_exit_features_writer(cur, close_fills: int) -> tuple[str, str]:
    """[3] EXIT-FEATURES-TABLE-1 Rust writer — expect 1:1 with close_fills."""
    n = _scalar(cur,
        "SELECT COUNT(*) FROM learning.exit_features "
        "WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'"
    )
    if close_fills == 0:
        return ("WARN", f"no close_fills baseline, exit_features={n} unscoreable")
    delta = abs(n - close_fills)
    if delta > max(3, close_fills // 3):
        return ("FAIL", f"exit_features_24h={n} vs close_fills={close_fills} (delta {delta}) — writer broken")
    return ("PASS", f"exit_features_24h={n} vs close_fills={close_fills} (delta {delta})")


def check_phys_lock_runtime(cur) -> tuple[str, str]:
    """[4] TRACK-P v2 phys_lock runtime fire rate — expect ≥1 per 24h if edge populated.

    Pattern note (RUST-DOUBLE-PREFIX-1 2026-04-23 post-fix): the upstream
    double-prefix bug was rooted out at the single `step_6_risk_checks.rs`
    emission site (Option B via `build_risk_close_tag`), so rows now land as
    canonical `strategy_name = "risk_close:phys_lock_gate4_giveback"` (single
    prefix). The healthcheck pattern is therefore restored to the strict
    `risk_close:phys_lock_%` form. The temporary-tolerant `risk_close:%phys_lock_%`
    pattern (commit `21e3d5e`) is intentionally **withdrawn**: keeping it would
    hide any future recurrence of the double-prefix regression — we want this
    check to go red again if the invariant breaks.

    Pattern note（RUST-DOUBLE-PREFIX-1 2026-04-23 修復後）：雙前綴 bug 已在單一
    `step_6_risk_checks.rs` emission 點（`build_risk_close_tag` Option B）根治，
    所有 PHYS-LOCK 列現以標準 `strategy_name = "risk_close:phys_lock_gate4_giveback"`
    （單前綴）寫入。Pattern 恢復為嚴格 `risk_close:phys_lock_%` 形式。
    原容錯 `risk_close:%phys_lock_%`（commit `21e3d5e`）刻意**收回**：保留會遮蔽
    未來雙前綴 regression，本檢查必須在 invariant 破壞時再次亮紅。
    """
    n_24h = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:phys_lock_%'"
    )
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:phys_lock_%'"
    )
    if n_7d == 0:
        return ("FAIL", f"phys_lock_* 7d=0 — Priority 6 runtime 完全 dead (P0-13/P0-14)")
    if n_24h == 0:
        return ("WARN", f"phys_lock_* 24h=0 (7d={n_7d}) — 近期停火，查 edge_estimates / atr coverage")
    return ("PASS", f"phys_lock_* 24h={n_24h} (7d={n_7d})")


def check_micro_profit_fire(cur) -> tuple[str, str]:
    """[5] RETIRED — legacy COST EDGE gate replaced by PHYS-LOCK v2.

    Background / 背景:
      The legacy COST EDGE gate (MICRO-PROFIT-FIX-1, 2026-04-17) was permanently
      removed from `risk_checks.rs` Priority 6 by TRACK-P-V2-SWAP-1
      (commit 306993e, 2026-04-22). The replacement is `physical_micro_profit_lock_v2`
      which emits `risk_close:phys_lock_*` tags — covered by [4] phys_lock_runtime.
      `risk_checks.rs:250-264` keeps the old block as a comment for historical
      reference only ("DEPRECATED ... Do not re-enable without design review").

      Therefore `strategy_name LIKE 'risk_close:COST EDGE%'` will never increment
      again; once the 7d window slides past 2026-04-22, both counts become 0
      forever. Continuing to FAIL/WARN on it produces a permanent false alarm
      (24h=0 since the swap, eventually 7d=0 too) that masks real signals in
      the cron summary.

      傳統 COST EDGE gate（MICRO-PROFIT-FIX-1）已於 2026-04-22 commit 306993e
      被 TRACK-P-V2-SWAP-1 永久移除，由 `physical_micro_profit_lock_v2`
      取代，產出 `risk_close:phys_lock_*` 標籤——由 [4] phys_lock_runtime
      接管監控。本 check 永遠回 PASS（informational only），保留歷史殘留計數
      供 audit；要看 micro-profit-lock 是否健康請看 [4]。

    This check is intentionally kept (not deleted) so the cron output retains
    a stable check-id mapping; it just no longer fires alarms.
    本 check 故意保留（不刪），維持 cron 輸出 check-id 穩定；不再發出告警。
    """
    n_24h = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '24 hours' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:COST EDGE%'"
    )
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:COST EDGE%'"
    )
    return ("PASS",
            f"RETIRED (replaced by [4] phys_lock_runtime, see TRACK-P-V2-SWAP-1 "
            f"commit 306993e); residue 24h={n_24h} 7d={n_7d}")


def check_trailing_stop_fire(cur) -> tuple[str, str]:
    """[6] TRAILING STOP fire rate — expect ≥1 per 7d."""
    n_7d = _scalar(cur,
        "SELECT COUNT(*) FROM trading.fills "
        "WHERE ts > now() - interval '7 days' "
        "AND engine_mode = 'demo' "
        "AND strategy_name LIKE 'risk_close:TRAILING STOP%'"
    )
    if n_7d == 0:
        return ("FAIL", f"TRAILING STOP 7d=0 — 所有倉位的 peak 都 < activation_pct?")
    return ("PASS", f"TRAILING STOP 7d={n_7d}")


def check_edge_estimates_freshness() -> tuple[str, str]:
    """[7] settings/edge_estimates.json mtime < 90 min (scheduler hourly).

    G6-01 [7a] (2026-04-24): added expected-minimum cell-count guard. The
    QA audit (§2.2 #2) flagged that the existing freshness + structure check
    cannot distinguish "JSON written hourly with 1 cell" (= near-empty
    estimator output, mostly useless for downstream cost_gate) from "JSON
    written with full coverage". 2026-04-24 verified Reality: JSON had only
    **1 cell** despite CLAUDE.md narrative claiming 162 — exactly the
    coverage-collapse failure mode this guard catches. We now FAIL when
    populated cells < `MIN_EXPECTED_CELLS` (=10, conservative floor matching
    OPENCLAW's ~25 active strategy×symbol pairs). The 90-min freshness +
    structure parse + dormant-prefix breakdown checks are preserved as
    layered guards above this new floor.

    [7] settings/edge_estimates.json mtime < 90 min（scheduler 每小時）。
    G6-01 [7a]（2026-04-24）：新增最低 cell 數守衛 — QA audit §2.2 #2 指
    現有 freshness + 結構檢查無法區分「按時寫入但只 1 cell」（等於空輸出，
    cost_gate 無法用）與「全覆蓋」。2026-04-24 實測 JSON 只 1 cell（vs
    CLAUDE.md 宣稱 162），正是此守衛要 catch 的 coverage-collapse 模式。
    populated < `MIN_EXPECTED_CELLS`（=10，保守底線匹配 OPENCLAW 約 25 active
    strategy×symbol pair）即 FAIL。原 freshness + 結構 + dormant prefix 檢查
    皆保留為堆疊防線。
    """
    # G6-01 [7a]: minimum cell count below which the JSON is "freshly written
    # but useless" — cost_gate / phys_lock fall back to defaults. Conservative
    # floor; raise to 25 once scheduler stabilises post-G1-01 recovery.
    # G6-01 [7a]：低於此 cell 數視為「按時寫入但無用」— cost_gate / phys_lock
    # 改用 default。保守底線 10；待 G1-01 scheduler 恢復穩定後可拉到 25。
    MIN_EXPECTED_CELLS = 10

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    p = base / "settings" / "edge_estimates.json"
    if not p.exists():
        return ("FAIL", f"edge_estimates.json 不存在 at {p}")
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    age_min = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 60.0
    if age_min > 90:
        return ("FAIL", f"edge_estimates.json age {age_min:.0f} min — scheduler 可能掛了")
    if age_min > 65:
        return ("WARN", f"edge_estimates.json age {age_min:.0f} min — 略過 hourly 節奏")
    # P0-14 RCA 2026-04-22 修正：JSON 是 flat map（key = "{strategy}::{symbol}"），不是
    # 「cells array」。原 `.get("cells", [])` 永遠回 [] 空。改成 flat map 遍歷，並同時
    # 計算 strategy prefix 分布（驗 H4 — `bybit_sync` / `orphan_*` / `dust_*` 等
    # runtime owner_strategy 是否有對應 cell）。
    # P0-14 RCA 2026-04-22 fix: JSON is a flat map (key = "{strategy}::{symbol}")
    # not a "cells array". The old `.get("cells", [])` always returned []. This
    # walks the flat map and also breaks down by strategy prefix to verify H4
    # (whether runtime owner_strategy values — bybit_sync / orphan_* / dust_* —
    # have matching cells at all).
    try:
        data = json.load(p.open())
        # Flat map path — skip meta keys (anything starting with "_" or matching
        # known aggregate names like "grand_mean_bps" / "generated_at").
        meta_keys = {"grand_mean_bps", "generated_at", "n_total", "version"}
        cell_items = {
            k: v for k, v in data.items()
            if isinstance(v, dict) and not k.startswith("_") and k not in meta_keys
        }
        total = len(cell_items)
        populated = sum(
            1 for v in cell_items.values() if v.get("shrunk_bps") is not None
        )
        # strategy prefix breakdown（用於 P0-14 H4 判斷）
        prefixes: dict[str, int] = {}
        for k in cell_items:
            prefix = k.split("::", 1)[0] if "::" in k else k
            prefixes[prefix] = prefixes.get(prefix, 0) + 1
        prefix_summary = ",".join(f"{p}:{n}" for p, n in sorted(prefixes.items()))
        cov = populated / total if total else 0.0
        msg = (f"edge_estimates.json age {age_min:.0f}m, "
               f"populated {populated}/{total} ({cov:.1%}), "
               f"prefixes[{prefix_summary or 'NONE'}]")
        if total == 0:
            return ("FAIL", msg + " — JSON 無 cells（scheduler first-run 或完全停寫）")
        # G6-01 [7a]: cell-count floor — JSON exists + fresh but coverage
        # collapsed. This is the 2026-04-24 "1-cell" failure mode RCA flag.
        # G6-01 [7a]：cell 數底線 — JSON 存在且新鮮但覆蓋崩潰。
        # 即 2026-04-24 「1 cell」失效模式 RCA 的指紋。
        if populated < MIN_EXPECTED_CELLS:
            return ("FAIL", msg + f" — populated {populated} < min_expected {MIN_EXPECTED_CELLS} "
                    "(coverage collapse; cost_gate fallback active; G1-01 scheduler diagnosis)")
        # H4 指紋：若 runtime 有 bybit_sync/orphan/dust 持倉但 JSON 無對應 prefix
        known_dormant = {"bybit_sync", "orphan_adopted", "orphan_frozen", "dust_frozen"}
        missing_dormant = known_dormant - set(prefixes.keys())
        if missing_dormant:
            return ("WARN", msg + f" — P0-14 H4 indicator：JSON 缺 {sorted(missing_dormant)} prefix cells")
        if cov < 0.3:
            return ("WARN", msg + " — low coverage")
        return ("PASS", msg)
    except Exception as e:
        return ("WARN", f"edge_estimates.json age {age_min:.0f}m, parse error: {e}")


def check_model_registry_freshness(cur) -> tuple[str, str]:
    """[9] learning.model_registry latest production model age — INFRA-PREBUILD-1 Part B.

    Phase 1a/2: registry is empty (no training runs yet). PASS with explicit
    "empty" message so operator knows this is expected dormancy and not a bug.

    Phase 3+ (once production models land): latest production `train_date` per
    slot should be within 30 days — PSI/drift mitigation. Thresholds:
    - table missing → FAIL (V023 not applied)
    - no production row → PASS + "empty" (Phase 1a/2 expected)
    - latest production row train_date within 30d → PASS
    - 30d < age ≤ 60d → WARN (retraining overdue)
    - age > 60d → FAIL (model likely stale, drift risk)

    [9] learning.model_registry 最新 production model 齡期。Phase 1a/2 空表屬預期；
    Phase 3+ 要求最新 production model train_date 30 天內。
    """
    try:
        cur.execute("""
            SELECT to_regclass('learning.model_registry') IS NOT NULL
        """)
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.model_registry missing — V023 not applied")

    # Per-slot latest-production max age: for each (strategy, engine_mode,
    # quantile) with at least one production row, find the most recent
    # train_date. Report the MIN across slots (the oldest slot is the bottleneck).
    # 每 slot 最新 production 的最大齡：跨 slots 取最小（最舊 slot = 瓶頸）。
    try:
        cur.execute("""
            WITH latest AS (
                SELECT strategy, engine_mode, quantile,
                       MAX(train_date) AS last_train_date
                FROM learning.model_registry
                WHERE canary_status = 'production'
                GROUP BY strategy, engine_mode, quantile
            )
            SELECT
                COUNT(*)::int                         AS production_slots,
                MIN(last_train_date)                  AS oldest_train_date,
                MAX(last_train_date)                  AS newest_train_date
            FROM latest
        """)
        slots, oldest, newest = cur.fetchone()
    except Exception as e:
        return ("WARN", f"registry query failed: {e}")

    if slots == 0:
        return (
            "PASS",
            "model_registry production slots=0 (expected in Phase 1a/2; flip once "
            "training pipeline writes first row via run_training_pipeline.py)",
        )

    # Compute age in days from oldest slot's train_date.
    # 以最舊 slot 的 train_date 計算天數。
    if oldest is None:
        return ("PASS", f"model_registry production slots={slots} but no train_date set")
    now = datetime.now(timezone.utc).date()
    age_days = (now - oldest).days
    msg = (
        f"model_registry production slots={slots}, "
        f"oldest={oldest} ({age_days}d ago), newest={newest}"
    )
    if age_days > 60:
        return ("FAIL", msg + " — oldest production model >60d, retrain overdue")
    if age_days > 30:
        return ("WARN", msg + " — oldest production model >30d, retrain due")
    return ("PASS", msg)


def check_intents_writer_ratio(cur) -> tuple[str, str]:
    """[10] trading.intents vs trading.orders 24h ratio per active engine_mode
    — P1-12 post-mortem guard.

    Context: on 2026-04-17, ``trading.intents`` took zero rows for the entire
    day across demo+live_demo while ``trading.orders``/``fills``/``risk_verdicts``
    kept writing normally (e.g. demo 4/17 had 1755 orders but 0 intents;
    live_demo 4/17 had 190 orders but 0 intents, and stayed broken 4/16-4/19).
    The P1-12 "bb_reversion 100% blocked" framing was actually a symptom of
    this whole-table intents-writer silent outage. This check catches recurrence.

    Coverage: (demo, live_demo). Per-mode evaluation — each mode gets its own
    verdict, then composite status = worst across modes. Skip any mode with
    orders_24h=0 (engine quiet). ``paper`` is excluded — PAPER-DISABLE-1 makes
    paper pipeline opt-in (OPENCLAW_ENABLE_PAPER=1), so silence is expected
    default; if paper is actively spawned and the writer silently dies, the
    operator is already in an investigation path for paper separately.

    Heuristic: demo 4/20-23 healthy baseline shows intents/orders ≈ 0.70-0.87
    (orders include ``strategy_close:*`` / ``risk_close:*`` tags that originate
    downstream of the intent stage, so ratio < 1.0 is normal). Per-mode:
        - orders=0 → skip (engine quiet)
        - orders>0 + intents=0 → FAIL (4/17-style outage fingerprint)
        - ratio < 0.3 → WARN (writer under-firing)
        - ratio ≥ 0.3 → PASS

    [10] trading.intents / orders 24h 比率守衛，逐 engine_mode 判定（P1-12
    2026-04-17 全天斷裂事件 post-mortem）：當時 risk_verdicts / orders / fills
    都正常寫，唯獨 intents 整天 0 rows —— **demo 與 live_demo 同時受災**，
    live_demo 更延續 4/16-4/19 四天。原只查 demo 的版本無法捕捉 live_demo
    未來再啟用後的復發。此 check 覆蓋 (demo, live_demo)，任一 mode orders>0 +
    intents=0 即 FAIL；paper 排除（OPENCLAW_ENABLE_PAPER=1 opt-in，預設 dormant）。
    """
    # Defensive rollback: if an earlier check aborted the transaction (e.g.
    # check [9] model_registry hitting a schema mismatch under Phase 1a), the
    # cursor is poisoned until rollback. Each check should be transactionally
    # independent — so we clear any dangling aborted-tx state before running.
    # 防禦式 rollback：前 check 若打斷 transaction（例如 [9] model_registry schema
    # 不匹配），後續 query 會全被 "transaction aborted" 拒絕。每 check 獨立 — 先清。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    modes = ("demo", "live_demo")
    per_mode: list[tuple[str, str, str]] = []  # (mode, status, short_msg)
    try:
        for mode in modes:
            cur.execute(
                "SELECT COUNT(*) FROM trading.orders "
                "WHERE ts > now() - interval '24 hours' AND engine_mode = %s",
                (mode,),
            )
            orders_n = int(cur.fetchone()[0] or 0)
            cur.execute(
                "SELECT COUNT(*) FROM trading.intents "
                "WHERE ts > now() - interval '24 hours' AND engine_mode = %s",
                (mode,),
            )
            intents_n = int(cur.fetchone()[0] or 0)

            if orders_n == 0:
                per_mode.append((mode, "SKIP", f"{mode}: quiet (orders=0)"))
                continue
            if intents_n == 0:
                per_mode.append((
                    mode, "FAIL",
                    f"{mode}: intents=0 / orders={orders_n} — writer silent-dead (4/17 fingerprint)",
                ))
                continue
            ratio = intents_n / orders_n
            seg = f"{mode}: intents={intents_n}/orders={orders_n} (ratio {ratio:.2f})"
            if ratio < 0.3:
                per_mode.append((mode, "WARN", seg + " under-firing"))
            else:
                per_mode.append((mode, "PASS", seg))
    except Exception as e:
        return ("WARN", f"intents/orders 24h query failed: {e}")

    # Composite: worst wins (FAIL > WARN > PASS > SKIP-only).
    # 彙總：最差者勝（FAIL > WARN > PASS > 只有 SKIP 代表全 engine quiet）。
    statuses = [s for _, s, _ in per_mode]
    summary = " | ".join(m for _, _, m in per_mode)
    if "FAIL" in statuses:
        return ("FAIL", summary + " — check Rust trading_writer intent INSERT + DB pool")
    if "WARN" in statuses:
        return ("WARN", summary + " — healthy baseline 0.70-0.87")
    if all(s == "SKIP" for s in statuses):
        return ("PASS", summary + " — all engines quiet, nothing to compare")
    return ("PASS", summary)


def _read_bb_breakout_active_from_toml() -> tuple[bool | None, str]:
    """G2-06 (2026-04-26): parse `[bb_breakout].active` from
    `settings/strategy_params_demo.toml`.

    Returns ``(value, diagnostic)``. ``value`` is True/False on successful
    parse + key lookup, ``None`` on any fail-soft condition (file missing /
    parse error / key absent / non-bool). ``diagnostic`` carries the
    human-readable reason for the ``None`` branch.

    Mirrors `_read_shadow_enabled_from_toml` shape; uses Python 3.11+
    ``tomllib`` (already used elsewhere in this codebase). No external
    dependency added. Reads the **actual value** rather than mtime as a
    state proxy — operator can hand-edit TOML and mtime would skew.

    G2-06：讀 demo strategy_params TOML 的 `[bb_breakout].active` 真值，
    fail-soft 回 ``None``。與 `_read_shadow_enabled_from_toml` 同形狀。
    用 tomllib（3.11+，codebase 既有），刻意取真值而非 mtime。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return (None, "tomllib unavailable (Python <3.11?)")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "strategy_params_demo.toml"

    if not toml_path.exists():
        return (None, f"strategy_params_demo.toml not found at {toml_path}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        # Fail-soft: TOML parse error degrades to original triage logic.
        # fail-soft：TOML parse 失敗則降級走原 triage。
        return (None, f"TOML parse error: {e}")

    section = data.get("bb_breakout")
    if not isinstance(section, dict):
        return (None, "[bb_breakout] section absent in strategy_params_demo.toml")

    val = section.get("active")
    if not isinstance(val, bool):
        return (None, f"[bb_breakout].active missing or non-bool (got {val!r})")

    return (val, "ok")


def check_disabled_strategy_inventory() -> tuple[str, str]:
    """[18] disabled-strategy inventory — pure observability, never FAIL.

    G2-06 (2026-04-26): CLAUDE.md §三 drift防線 (G6-04). When a strategy is
    disabled at TOML level (`active=false`), we want it to remain visible
    in healthcheck output so future audits can't "forget" disabled
    strategies. This check parses `settings/strategy_params_demo.toml`,
    walks every `[<strategy>]` section, and lists those with
    ``active=false``. Always returns PASS — purely informational.

    Phase 1a / first-run note: when no strategies are disabled, the check
    reports "no disabled strategies" + PASS (still useful as a
    structural check that the TOML parse works at all).

    [18] disabled 策略 inventory — 純觀察性，永遠不 FAIL。
    G2-06（2026-04-26）：CLAUDE.md §三 drift 防線（G6-04）。策略 TOML
    disable（active=false）時須在 healthcheck 輸出可見，避免未來 audit
    「忘了還有這策略」誤撿。讀 demo TOML，列出 active=false 策略。
    永遠 PASS（純記錄性）。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return ("PASS", "tomllib unavailable (Python <3.11?), inventory unavailable")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "strategy_params_demo.toml"

    if not toml_path.exists():
        return ("PASS", f"strategy_params_demo.toml not found at {toml_path} (skip)")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        return ("PASS", f"TOML parse error (skip): {e}")

    disabled: list[str] = []
    active: list[str] = []
    for name, section in data.items():
        if not isinstance(section, dict):
            continue
        val = section.get("active")
        if isinstance(val, bool):
            if val is False:
                disabled.append(name)
            else:
                active.append(name)

    if not disabled:
        return (
            "PASS",
            f"no disabled strategies (active count={len(active)}: {', '.join(sorted(active)) or '(none)'})",
        )

    return (
        "PASS",
        f"disabled strategies: {', '.join(sorted(disabled))} "
        f"(active count={len(active)}: {', '.join(sorted(active)) or '(none)'})",
    )


def check_bb_breakout_post_deadlock_fix(cur) -> tuple[str, str]:
    """[12] bb_breakout post-FIX-26-DEADLOCK-1 fill rate — P1-11 (1) Phase 1.

    G2-06 (2026-04-26): If `[bb_breakout].active=false` in
    `settings/strategy_params_demo.toml` (per PA RFC `2026-04-26 G2-06`
    permanent disable), this check returns PASS (skip) immediately —
    silencing the FAIL noise so other dormancy checks remain visible.
    Re-enabling the strategy (active=true) restores the original 3-state
    triage logic without further code changes.

    Context: 2026-04-24 sweep + Rust commit ``bcc5401`` discovered + fixed
    `squeeze_detected_ms` permanent-deadlock bug. Pre-fix, bb_breakout had
    14d 0 fills (symbol-locked after first failed-entry expiry). Post-fix
    + ``--rebuild`` deploy + multiple validation cycles still showed 0 fills,
    confirming F1 1m bandwidth mis-scale is structural (not deadlock
    residue). PA RFC 2026-04-26 chose option C (permanent disable).

    Three-state triage (when active=true):
      - 7d entries (`strategy_name='bb_breakout'`, no risk_close prefix):
        - 0 over 7d post-deploy → FAIL (fix didn't work or thresholds still
          mis-scaled per F1; check engine binary rebuild + thresholds)
        - 1-5 over 7d → WARN (out of dormant but very low; threshold tuning
          per Phase 2 backlog needed)
        - ≥6 over 7d → PASS (operating normally)
      - Pre-deploy state: this check fails until ``--rebuild`` deploys the
        Rust fix. Operator should mark this expected until that happens.

    The check looks for the **engine PID start time** as a deploy proxy
    (`/tmp/openclaw/engine_pid` mtime); if absent, falls back to a
    7d-window strategy fill count without deploy gating.

    [12] FIX-26-DEADLOCK-1 部署後 bb_breakout 是否真的脫離 permanent-dormant。
    G2-06（2026-04-26）：若 demo TOML `[bb_breakout].active=false`（PA RFC
    永久 disable）則直接 PASS 跳過，避免持續 FAIL 噪音蓋過真 alarm；TOML
    flip 回 true 後自動恢復原三態邏輯，無需改碼。
    7d entry 數三態（active=true 時）：0=FAIL（修沒生效或閾值還錯）/
    1-5=WARN（出 dormant 但極低）/ >=6=PASS（正常運作）。
    """
    # G2-06 (2026-04-26): TOML-driven disable skip — PA RFC permanent disable.
    # Read demo strategy_params TOML; if [bb_breakout].active=false, skip.
    # Fail-soft: any TOML read error falls through to original triage logic.
    # G2-06：讀 demo TOML，active=false 則跳過；TOML 讀失敗 fail-soft 走原邏輯。
    bb_active, _diag = _read_bb_breakout_active_from_toml()
    if bb_active is False:
        return (
            "PASS",
            "[12] bb_breakout disabled by G2-06 (active=false in TOML); fill check skipped",
        )

    try:
        n_7d = _scalar(cur,
            "SELECT COUNT(*) FROM trading.fills "
            "WHERE ts > now() - interval '7 days' "
            "AND engine_mode = 'demo' "
            "AND strategy_name = 'bb_breakout'"
        )
    except Exception as e:
        return ("WARN", f"bb_breakout 7d query failed: {e}")

    # Deploy proxy: check engine PID file mtime as a "since-rebuild" timestamp.
    # 部署代理：用 engine PID 檔 mtime 作「自 rebuild 起算」時間。
    deploy_age_hint = ""
    try:
        pid_path = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")) / "engine_pid"
        if pid_path.exists():
            mtime = datetime.fromtimestamp(pid_path.stat().st_mtime, tz=timezone.utc)
            age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
            deploy_age_hint = f", engine_pid age {age_h:.1f}h"
            # If engine deployed within last 7d, the "7d window" includes
            # pre-fix bars. Operator should re-eval after >7d of post-fix runtime.
            # 引擎部署 <7d 時 7d 窗包含修前資料，需等 >7d 才有 clean baseline。
            if age_h < 168:  # < 7d
                deploy_age_hint += " (window includes pre-fix data, baseline pending)"
    except Exception:
        pass

    if n_7d == 0:
        return (
            "FAIL",
            f"bb_breakout 7d entries=0{deploy_age_hint} — FIX-26-DEADLOCK-1 fix "
            f"may not be deployed (--rebuild?) or thresholds still mis-scaled (P1-11 F1)",
        )
    if n_7d < 6:
        return (
            "WARN",
            f"bb_breakout 7d entries={n_7d}{deploy_age_hint} — out of permanent-dormant "
            f"but very low; Phase 2 threshold tuning recommended",
        )
    return (
        "PASS",
        f"bb_breakout 7d entries={n_7d}{deploy_age_hint} — operating normally post-deadlock-fix",
    )


def _read_shadow_enabled_from_toml() -> tuple[bool | None, str]:
    """INFRA-PREBUILD-1 L2-5 (2026-04-23): parse `[exit].shadow_enabled` from
    `settings/risk_control_rules/risk_config_demo.toml`.

    Returns a ``(value, diagnostic)`` tuple. ``value`` is True/False when the
    TOML parse and key lookup both succeed, ``None`` on any fail-soft condition
    (file missing / parse error / key absent). ``diagnostic`` carries the
    human-readable reason for the ``None`` branch so check_shadow_exit_ratio
    can annotate its PASS/FAIL message.

    Uses Python 3.11+ ``tomllib`` (already used elsewhere in this codebase —
    see paper_trading_routes.py:1044). No external dependency added.

    We deliberately parse the **actual value** rather than trusting the file
    mtime as a "flag state" proxy — operators can hand-edit the TOML and the
    mtime skew would desynchronise. This is the hot-reload contract: state
    comes from the parsed `shadow_enabled` key, nothing else.

    L2-5 TOML 解析：讀 `[exit].shadow_enabled` 真值，fail-soft 回 ``None``。
    用 tomllib（3.11+，codebase 既有使用）；刻意取真值而非 mtime，因為
    operator 可能手編 TOML 導致 mtime 與 flag 狀態不同步。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return (None, "tomllib unavailable (Python <3.11?)")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "risk_control_rules" / "risk_config_demo.toml"

    if not toml_path.exists():
        return (None, f"risk_config_demo.toml not found at {toml_path}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        # Fail-soft: TOML parse error does not flag the whole pipeline dead;
        # check_shadow_exit_ratio degrades to its pre-L2-5 ambiguous message.
        # fail-soft：TOML parse 失敗不讓整條 pipeline 紅，check 降級為原本訊息。
        return (None, f"TOML parse error: {e}")

    exit_section = data.get("exit")
    if not isinstance(exit_section, dict):
        return (None, "[exit] section absent in risk_config_demo.toml")

    val = exit_section.get("shadow_enabled")
    if not isinstance(val, bool):
        return (None, f"[exit].shadow_enabled missing or non-bool (got {val!r})")

    return (val, "ok")


def check_shadow_exit_ratio(cur) -> tuple[str, str]:
    """[8] learning.decision_shadow_exits activity — INFRA-PREBUILD-1 Part A.

    Shadow mode is OFF by default (ExitConfig.shadow_enabled=false). L2-5
    audit (2026-04-23) upgraded this check from the ambiguous "24h=0 → PASS
    (if flag ON this is silent-dead)" message to a deterministic three-state
    triage by actively parsing `settings/risk_control_rules/risk_config_demo.toml`
    for the `[exit].shadow_enabled` value:

    - `shadow_enabled=false` + 24h rows=0 → PASS (dormant as designed)
    - `shadow_enabled=true`  + 24h rows=0 → FAIL silent-dead (explicit alarm,
        exit 1 via the `any_fail` branch in main)
    - `shadow_enabled=true`  + 24h rows>0 → PASS with disagreement breakdown
        (Phase 2 agreement target ≥60%)
    - table missing → FAIL (V021 migration not applied)
    - TOML parse fails → degrade to pre-L2-5 ambiguous PASS message so a
        healthcheck-side IO hiccup does not flag the whole pipeline dead

    The TOML value is read **at check time** (no caching); operator hot-
    reloads via TOML edit or IPC patch_risk_config flip the state machine
    immediately on the next healthcheck pass.

    [8] decision_shadow_exits 三態診斷（L2-5，2026-04-23）：
    - flag=false + 24h=0 → PASS（dormant 預期）
    - flag=true  + 24h=0 → FAIL（silent-dead，Phase 2 啟動後 writer 掛掉指紋）
    - flag=true  + 24h>0 → PASS + 分歧比率
    - TOML parse 失敗 → 降級回原始 ambiguous 訊息（不讓 healthcheck 自身 IO
      問題讓整條 pipeline 亮紅）
    """
    # Table existence check — V021 applied?
    # 檢查表是否存在（V021 是否已套用？）。
    try:
        cur.execute("""
            SELECT to_regclass('learning.decision_shadow_exits') IS NOT NULL
        """)
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.decision_shadow_exits missing — V021 not applied")

    # Row count + disagreement breakdown over 24h window.
    # 24h 窗口：行數 + 分歧比率。
    try:
        cur.execute("""
            SELECT
                COUNT(*)::int                                        AS total,
                COUNT(*) FILTER (WHERE disagreed)::int               AS disagreed_n,
                COUNT(DISTINCT engine_mode)::int                     AS engines,
                MAX(ts) AT TIME ZONE 'UTC'                            AS last_ts
            FROM learning.decision_shadow_exits
            WHERE ts > now() - interval '24 hours'
        """)
        total, disagreed_n, engines, last_ts = cur.fetchone()
    except Exception as e:
        return ("WARN", f"shadow_exits 24h query failed: {e}")

    # INFRA-PREBUILD-1 P3-4 (2026-04-23): 加查 last_1h 作為 channel-stall 指紋。
    # 若 24h 有大量 rows 但 last_1h=0 → writer/channel 近期停擺（overflow 或 lag），
    # 24h 累積掩蓋了近期狀態。operator 看到 `24h=100, last_1h=0` 即可直覺判斷。
    # 純 observability context，不加決策邏輯（無新 WARN/FAIL 觸發條件）。
    #
    # INFRA-PREBUILD-1 P3-4（2026-04-23）：加查 last_1h 作 channel-stall 指紋。
    # 若 24h 有量但 last_1h=0 → 近期 writer/channel 停擺，24h 累積遮蔽近期；
    # operator 肉眼見 `24h=100, last_1h=0` 即秒懂。純觀察 context，不加決策邏輯。
    try:
        cur.execute("""
            SELECT COUNT(*)::int
            FROM learning.decision_shadow_exits
            WHERE ts > now() - interval '1 hour'
        """)
        last_1h = cur.fetchone()[0]
    except Exception:
        # Sub-query best-effort — don't fail the whole check on this.
        # 次要查詢 best-effort — 失敗不拖垮整體檢查。
        last_1h = -1  # sentinel for "query failed"

    # L2-5 (2026-04-23): active triage via TOML parse.
    # L2-5（2026-04-23）：主動 TOML 三態診斷。
    shadow_enabled, toml_diag = _read_shadow_enabled_from_toml()

    if total == 0:
        if shadow_enabled is None:
            # Fail-soft: TOML parse failed → fall back to ambiguous message
            # (pre-L2-5 behaviour). PASS so healthcheck self-IO glitch does
            # not flag the pipeline dead.
            # fail-soft：TOML parse 失敗 → 降級回原 ambiguous 訊息。
            return (
                "PASS",
                f"decision_shadow_exits 24h=0 "
                f"(shadow_enabled state unknown: {toml_diag}; "
                f"if flag ON this would be silent-dead)",
            )
        if shadow_enabled is True:
            # Flag ON + 0 rows → silent-dead (writer broken or channel full).
            # FAIL causes main()'s any_fail → exit 1.
            # flag=true + 24h=0 → silent-dead；main() any_fail → exit 1。
            return (
                "FAIL",
                "decision_shadow_exits 24h=0 BUT [exit].shadow_enabled=true "
                "— silent-dead writer (Phase 2 active but zero rows). "
                "Check Rust shadow_exit_writer log + channel capacity + "
                "ExitConfig hot-reload propagation.",
            )
        # shadow_enabled is False → dormant as designed.
        # shadow_enabled=false → 預期 dormant。
        return (
            "PASS",
            "decision_shadow_exits 24h=0 (shadow_enabled=false, dormant as designed)",
        )

    agreement_pct = 100.0 * (1.0 - disagreed_n / total)
    last_1h_str = f"last_1h={last_1h}" if last_1h >= 0 else "last_1h=?"
    msg = (
        f"decision_shadow_exits 24h={total}, {last_1h_str}, disagreed={disagreed_n} "
        f"({100 - agreement_pct:.1f}%), engines={engines}, last_ts={last_ts}"
    )
    # Phase 2 agreement target ≥60% (Track P vs Combine+mock-ML).
    # Phase 2 一致性目標 ≥60%（Track P vs Combine+mock-ML）。
    if agreement_pct < 60.0:
        return ("WARN", msg + " — agreement <60% Phase 2 target")
    return ("PASS", msg)


def check_leader_election_health() -> tuple[str, str]:
    """[Xa] G6-01 (2026-04-24): edge_estimator_scheduler leader-lock health.

    The QA audit (§2.2 #5) flagged a blind spot: check [7] catches
    `edge_estimates.json` staleness but **cannot distinguish**:
      A. scheduler died entirely → eventually [7] FAILs after 90 min, AND
      B. the leader-lock holder PID died but the lock file survives → no
         worker re-elects itself → estimator silently dormant; [7] catches
         this only after 90 min with no narrative help on root cause; AND
      C. lock holder is alive but scheduler thread crashed → [7] eventually
         FAILs after 90 min but operator has no fast triage signal.

    EDGE-SCHEDULER-LEADER-1 (2026-04-23 commit `f32629c`) writes the leader
    PID into `$OPENCLAW_DATA_DIR/edge_scheduler.leader.lock` for operator
    debug (`cat <lock>` → leader PID). This check inspects:
      1. Lock file existence + mtime (stale = >24h since last leader touch).
      2. Lock holder PID liveness (`/proc/<pid>` on Linux; `ps` fallback).
      3. Cross-correlate with [7] freshness — if [7] failing AND lock dead
         → the diagnosis is "leader election broken" not "scheduler busy".

    Three-state output:
      - FAIL: lock missing entirely, or lock present but PID dead AND age > 1h
        (operator action: `rm <lock>`; restart api process to re-elect).
      - WARN: lock age >12h (stale-lock drift; restart at next maintenance).
      - PASS: lock present, PID alive, age <12h.

    Cross-platform: `/proc/<pid>` on Linux is the cheap path; macOS / fallback
    uses `os.kill(pid, 0)` which raises if PID dead. Both work without root.
    Fail-soft: any check-internal IO error → WARN (never FAIL on this check
    alone; we don't want a healthcheck plumbing bug to mask the real signal).

    [Xa] G6-01（2026-04-24）：edge_estimator_scheduler leader-lock 健康檢查。
    QA audit §2.2 #5 指 check [7] 抓不到「leader 死掉但 lock 沒清」的 silent
    death（worker 不重選舉，estimator 靜默 dormant），且 90 min 後 [7] 才
    亮紅，operator 缺快速 triage 信號。EDGE-SCHEDULER-LEADER-1（2026-04-23
    commit `f32629c`）把 leader PID 寫入 $OPENCLAW_DATA_DIR/
    edge_scheduler.leader.lock 供 operator `cat` debug。本 check：
      1. 檢查 lock 檔存在 + mtime（>24h 視為 stale）
      2. 檢查 lock 內 PID 是否存活（Linux 走 /proc，macOS fallback os.kill(0)）
      3. 與 [7] 互補：[7] FAIL + 本 check FAIL → 「leader election 壞」而非
         「scheduler 在跑」
    三態：FAIL（lock 缺 / PID 死 + age>1h）、WARN（age>12h）、PASS。
    跨平台：/proc 走 Linux 快路徑，os.kill(pid, 0) 雙平台 fallback。
    Fail-soft：本 check 內部 IO 錯一律 WARN，避免 plumbing bug 遮掩真信號。
    """
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    lock_path = data_dir / "edge_scheduler.leader.lock"

    if not lock_path.exists():
        # Distinguish "scheduler never ran" (lock never created) from
        # "scheduler ran then lock got rm'd" — both register as missing
        # and both warrant FAIL because no leader is currently holding it.
        # OPENCLAW_SCHEDULER_LEADER=0 (operator disable) is the only valid
        # path to no-lock + no-FAIL — we annotate that explicitly.
        # 區分「scheduler 從未跑」vs「跑後 lock 被刪」— 兩者都 FAIL，因為當前
        # 無 leader 持鎖。OPENCLAW_SCHEDULER_LEADER=0（operator 手動停用）是
        # 唯一合理的「無 lock 不 FAIL」路徑，我們明確標注。
        if os.environ.get("OPENCLAW_SCHEDULER_LEADER") == "0":
            return ("PASS", f"leader lock absent at {lock_path} — "
                    "OPENCLAW_SCHEDULER_LEADER=0 (operator disabled, expected)")
        return ("FAIL", f"leader lock missing at {lock_path} — "
                "edge_estimator_scheduler never elected (uvicorn dead? G1-01)")

    # Read lock metadata. mtime stays current as long as the leader process
    # holds the fd; OS releases on process exit, but the file inode persists
    # (sentinel mode). So mtime ~= last leader-acquire time, not "last write".
    # 讀 lock metadata。leader 持 fd 時 mtime 維持；OS 在 process 退出時釋放鎖，
    # 但 inode 留下（sentinel 模式）。所以 mtime ≈ 最近一次 leader 取得時間。
    try:
        mtime = datetime.fromtimestamp(lock_path.stat().st_mtime, tz=timezone.utc)
        age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
    except OSError as e:
        return ("WARN", f"leader lock stat failed: {e}")

    # Read PID from lock body — `_acquire_leader_lock` writes "<pid>\n" after
    # successful flock. May be empty if write failed (non-fatal in scheduler).
    # 從 lock 內容讀 PID — `_acquire_leader_lock` 在 flock 後寫入「<pid>\n」。
    # 若寫失敗（scheduler 端 non-fatal）內容會空。
    leader_pid: int | None = None
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
        if raw:
            leader_pid = int(raw.splitlines()[0])
    except (OSError, ValueError) as e:
        # PID malformed — surface as WARN with raw read for operator debug.
        # PID 格式壞 — WARN 並回顯原始內容供 operator debug。
        return ("WARN", f"leader lock at {lock_path} (age {age_h:.1f}h) — "
                f"PID read malformed: {e}")

    if leader_pid is None:
        # Lock acquired but PID write empty — partial init or scheduler crash
        # mid-acquire. Don't FAIL (lock-holder may still be alive), but WARN.
        # Lock 取得但 PID 寫入為空 — 初始化中斷或 scheduler 取鎖中崩潰。
        # 不 FAIL（持鎖者可能仍活）但 WARN。
        return ("WARN", f"leader lock at {lock_path} (age {age_h:.1f}h) — "
                "PID body empty (partial init? scheduler crash mid-acquire?)")

    # Check PID liveness. /proc/<pid> on Linux is cheapest; os.kill(pid, 0)
    # works on both Linux and macOS without sending an actual signal — raises
    # ProcessLookupError if PID doesn't exist, PermissionError if PID exists
    # but we lack rights (still proves it's alive).
    # PID 存活檢查。Linux 走 /proc 最便宜；os.kill(pid, 0) 雙平台不發訊號 —
    # 不存在則 ProcessLookupError；存在但無權限則 PermissionError（仍證活著）。
    pid_alive = False
    try:
        os.kill(leader_pid, 0)
        pid_alive = True
    except ProcessLookupError:
        pid_alive = False
    except PermissionError:
        # PID exists but other-user owned — we proved it's alive.
        # PID 存在但屬其他 user — 證明活著。
        pid_alive = True
    except OSError as e:
        # Other OS errors (rare) — fail-soft to WARN.
        # 其他 OSError（罕見）— fail-soft 為 WARN。
        return ("WARN", f"leader lock pid={leader_pid} liveness probe failed: {e}")

    if not pid_alive:
        # Dead leader + lock survives = the silent-death blind spot QA flagged.
        # Operator: rm <lock>; restart uvicorn process to re-elect.
        # 死 leader + lock 留存 = QA 指的 silent-death 盲點。
        # Operator 動作：rm <lock>; restart uvicorn 觸發重選舉。
        return ("FAIL", f"leader lock pid={leader_pid} DEAD (age {age_h:.1f}h, "
                f"lock at {lock_path}) — re-election blocked; operator: "
                f"`rm {lock_path}` + restart uvicorn")

    # PID alive — check age for staleness drift.
    # PID 活著 — 檢查 age 是否漂移過久。
    base_msg = (f"leader_pid={leader_pid} alive, lock_age={age_h:.1f}h, "
                f"path={lock_path}")
    if age_h > 24:
        return ("WARN", base_msg + " — lock >24h old (drift; restart at next maintenance)")
    return ("PASS", base_msg)


def check_pipeline_triangulation(cur, close_fills_24h: int) -> tuple[str, str]:
    """[Xb] G6-01 (2026-04-24): cross-pipeline triangulation between fills / labels / intents.

    QA audit §2.2 #4 flagged a blind spot: the 12 existing checks are each
    locally consistent (ratio ≥ N%, row count ≥ M, fire count ≥ K) but they
    **do not cross-reference each other**. A subtle pipeline-level failure can
    leave every individual check green while the aggregate telemetry is
    incoherent. Examples this check catches that individual [1]/[2]/[10]
    miss:

      A. **Duplicate-intent writer bug**: intents_24h = 3× orders_24h because
         an IPC retry loop double-emits the same intent. [10] rates 0.3-1.0 as
         under-firing / normal; it does **not** alarm on 3.0. Fills + labels
         look clean, but intent ledger is inflated — contaminates downstream
         auditing + strategy attribution.

      B. **Label-backfill lagging fill rate but above floor**: close_fills=50,
         labels=40 (ratio 0.80 PASS by [2]), intents=15 (ratio 0.30 PASS by
         [10]). Each looks OK; triangulation notices fills >> intents (3.3×)
         which points at engine emitting fills from a path that skips intent
         ledger (orphan adopter? phantom close?). This is the P0-4 / P0-5
         phantom-close fingerprint that [10] alone cannot surface because
         [10] compares intents to orders, not to fills.

      C. **Silent scale drift**: all three counts non-zero but one drifts 2+
         orders of magnitude vs the others over 24h. Without cross-check, a
         "fills=5 / labels=500" scenario (label backfiller looping on stale
         rows) passes [2] (ratio=100) without flagging the absurd mismatch.

    Three-state triage:
      - **FAIL**: any pairwise ratio outside the "plausible" band
        `[0.1, 10.0]` when all three anchors > 0 (severe divergence; silent
        corruption indicator).
      - **WARN**: any pairwise ratio outside `[0.3, 3.0]` (drift indicator,
        investigate).
      - **PASS**: all three pairwise ratios inside `[0.3, 3.0]`, or close_fills
        too low (< 5) to triangulate reliably (defer to [1]'s own FAIL/WARN).

    Fail-soft: if any of the 3 counts cannot be queried (schema drift, aborted
    transaction), downgrade to WARN with diag — do NOT let a healthcheck-side
    IO glitch shadow the triangulation signal.

    [Xb] G6-01（2026-04-24）：fills / labels / intents 跨管線三角驗證。
    QA audit §2.2 #4 指 12 個 check 彼此獨立（各驗自己門檻），不做交叉比對。
    許多管線級 bug（重複寫 intent、phantom fill、label backfill 失控循環）個別
    check 全綠但彙總不合理；本 check 做 pairwise ratio 檢查，覆蓋 [1]/[2]/[10]
    個別盲點。三態：全部 ratio ∈ [0.3, 3.0] = PASS；任一在 [0.1, 0.3) 或
    (3.0, 10.0] = WARN（drift）；任一超出 [0.1, 10.0] = FAIL（severe divergence）。
    Close_fills < 5 時樣本太小無法三角化，降級回 [1] 自身判決。
    Fail-soft：任一查詢失敗 WARN + diag，不讓 IO glitch 遮蔽信號。
    """
    # Defensive rollback: keep cursor clean in case an earlier check aborted
    # the transaction. Same pattern as check_intents_writer_ratio.
    # 防禦式 rollback：避免前 check 異常打斷 transaction 讓後續 query 全失敗。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Small-sample short-circuit: close_fills < 5 makes every ratio noisy.
    # Defer to [1]'s own WARN/FAIL verdict; emit PASS with an explicit note so
    # operator sees the triangulation was intentionally skipped, not silenced.
    # 樣本過小（close_fills < 5）比率完全不可信 — 降級 PASS + 明示被跳過，
    # 不要變成「沉默 PASS」讓 operator 以為真的三角化過。
    if close_fills_24h < 5:
        return (
            "PASS",
            f"triangulation skipped: close_fills_24h={close_fills_24h} < 5 "
            "(defer to [1] verdict; ratios unreliable at this sample size)",
        )

    # Query labels_24h (same filter as [2]) and intents_24h (same filter as [10]
    # but demo-only, since close_fills baseline is demo-scoped).
    # 查 labels_24h（同 [2]）與 intents_24h（同 [10]，demo-only 匹配 baseline）。
    try:
        cur.execute(
            "SELECT COUNT(*) FROM learning.decision_features "
            "WHERE label_filled_at > now() - interval '24 hours' "
            "AND label_net_edge_bps IS NOT NULL "
            "AND engine_mode = 'demo'"
        )
        labels_24h = int(cur.fetchone()[0] or 0)
    except Exception as e:
        return ("WARN", f"triangulation labels query failed: {e}")

    try:
        cur.execute(
            "SELECT COUNT(*) FROM trading.intents "
            "WHERE ts > now() - interval '24 hours' AND engine_mode = 'demo'"
        )
        intents_24h = int(cur.fetchone()[0] or 0)
    except Exception as e:
        return ("WARN", f"triangulation intents query failed: {e}")

    # Pairwise ratio analysis. Reference anchor = close_fills_24h.
    # fills:labels and fills:intents are most informative; labels:intents is
    # a secondary cross-check.
    # Pairwise 比率分析。參考錨 = close_fills_24h。
    def _ratio(a: int, b: int) -> float:
        """Safe ratio a/b; returns float('inf') on b=0, 0.0 on a=b=0.
        安全比率：b=0 時 inf，a=b=0 時 0.0，讓上層判 "one-sided" 分歧。"""
        if b == 0:
            return float("inf") if a > 0 else 0.0
        return a / b

    r_fl = _ratio(close_fills_24h, labels_24h)     # fills / labels
    r_fi = _ratio(close_fills_24h, intents_24h)    # fills / intents
    r_li = _ratio(labels_24h, intents_24h)         # labels / intents

    # Plausible / WARN / FAIL bands (symmetric around 1.0).
    # 合理 / WARN / FAIL 區間（對稱於 1.0）。
    WARN_LO, WARN_HI = 0.3, 3.0       # outside this → WARN
    FAIL_LO, FAIL_HI = 0.1, 10.0      # outside this → FAIL

    def _classify(r: float) -> str:
        """Return '', 'WARN', or 'FAIL' for a single ratio.
        單一比率分類：空字串（正常）/ WARN / FAIL。"""
        if r == 0.0 or r == float("inf"):
            # One-sided zero — e.g. fills>0 + labels=0. FAIL-grade because
            # either anchor totally missing despite baseline alive.
            # 單邊零 — 其中一方完全空，FAIL（基線活但某端完全斷）。
            return "FAIL"
        if r < FAIL_LO or r > FAIL_HI:
            return "FAIL"
        if r < WARN_LO or r > WARN_HI:
            return "WARN"
        return ""

    classes = {
        "fills/labels": (r_fl, _classify(r_fl)),
        "fills/intents": (r_fi, _classify(r_fi)),
        "labels/intents": (r_li, _classify(r_li)),
    }

    # Summarise pairwise ratios for operator readability. Use "inf" / "0.00"
    # sentinels for one-sided divergence; float('inf') formats as 'inf' so
    # explicit branch for clarity.
    # 總結 pairwise 比率供 operator 可讀。單邊分歧用 inf / 0.00 顯示。
    def _fmt(r: float) -> str:
        if r == float("inf"):
            return "inf"
        return f"{r:.2f}"

    pairs_str = ", ".join(
        f"{name}={_fmt(r)}{'[' + cls + ']' if cls else ''}"
        for name, (r, cls) in classes.items()
    )
    base = (
        f"close_fills={close_fills_24h}, labels={labels_24h}, intents={intents_24h} | "
        f"{pairs_str}"
    )

    # Composite verdict: FAIL wins > WARN wins > PASS.
    # 彙總：FAIL > WARN > PASS。
    statuses = [cls for _, (_, cls) in classes.items() if cls]
    if "FAIL" in statuses:
        return (
            "FAIL",
            base + " — severe pairwise divergence (duplicate writer / phantom "
            "close / label-backfill runaway; see RCA log)",
        )
    if "WARN" in statuses:
        return (
            "WARN",
            base + " — drift; inspect intent writer + label backfill lag",
        )
    return ("PASS", base)


def check_counterfactual_clean_window_growth() -> tuple[str, str]:
    """[11] EDGE-DIAG-1 Phase 3 gate — post-P013-clean bucket row/fire growth.

    MODULE_NOTE (EN): Phase 4 cron-side healthcheck for the "wait N days until
    post-P013-clean bucket accumulates ≥200 rows per FM bootstrap-CI threshold"
    passive-wait TODO (EDGE-DIAG-1 Phase 3 deferred 2026-04-24). Reads the
    latest `counterfactual_exit_replay_latest.json` at `$OPENCLAW_DATA_DIR/audit/`,
    extracts `by_window['post-P013-clean']` n_rows / cf_fired / per-strategy
    breakdown, snapshots today's summary to `audit/daily/YYYYMMDD.json`, and
    returns PASS (Phase 3 entry criteria met: ≥200 rows + {grid_trading,
    ma_crossover} each cf_fired ≥50 + orphan_frozen clean rows ≥20) / WARN
    (on-track with ETA) / FAIL (JSON stale >48h or n_rows regressed). Fail-soft
    on missing JSON / missing daily dir — WARN, not crash.

    MODULE_NOTE (中): Phase 4 cron 側健檢，被動等待 post-P013-clean bucket 累積
    ≥200 rows（FM bootstrap-CI 門檻）的 TODO（EDGE-DIAG-1 Phase 3 2026-04-24
    延後）。讀最新 `counterfactual_exit_replay_latest.json`，取
    `by_window['post-P013-clean']` 的 n_rows / cf_fired / 策略分佈；快照當日
    到 `audit/daily/YYYYMMDD.json`；三態返回 PASS（Phase 3 入場條件達）/
    WARN（累積中，附 ETA）/ FAIL（JSON >48h 未更新或 n_rows 倒退）。JSON
    / daily 目錄缺失 fail-soft 為 WARN，不 crash。
    """
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    audit_dir = data_dir / "audit"
    latest = audit_dir / "counterfactual_exit_replay_latest.json"
    daily_dir = audit_dir / "daily"

    if not latest.exists():
        return ("WARN", f"counterfactual_exit_replay_latest.json 不存在 at {latest} — cron 尚未首跑?")

    # Freshness guard — >48h stale means cron silent-dead.
    # Freshness：>48h 代表 cron 靜默掛掉。
    mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
    age_hours = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
    if age_hours > 48:
        return ("FAIL", f"counterfactual JSON age {age_hours:.1f}h > 48h — daily cron dead?")

    try:
        payload = json.load(latest.open())
    except Exception as e:
        return ("WARN", f"counterfactual JSON parse error: {e}")

    by_window = payload.get("by_window") or {}
    clean_rows = by_window.get("post-P013-clean")
    if clean_rows is None:
        return ("WARN",
                "by_window.post-P013-clean 缺失 — 檢查 cron wrapper 是否傳 --split-window")

    # Each entry in clean_rows is an aggregation group with keys:
    #   strategy_name / symbol / engine_mode / n_exits / per_model[model].cf_fired_count
    # 每 entry = aggregation group，欄位 strategy_name/symbol/n_exits/per_model[*].cf_fired_count。
    n_rows = 0
    per_strategy_fired: dict[str, int] = {}
    per_strategy_rows: dict[str, int] = {}
    for r in clean_rows:
        n = int(r.get("n_exits") or 0)
        n_rows += n
        strat = str(r.get("strategy_name") or "")
        per_strategy_rows[strat] = per_strategy_rows.get(strat, 0) + n
        pm = r.get("per_model") or {}
        # Prefer fee_only model; fall back to any single model for cf_fired.
        # 優先用 fee_only 模型；無則取任一模型的 cf_fired_count。
        fired = 0
        if isinstance(pm, dict):
            if "fee_only" in pm and isinstance(pm["fee_only"], dict):
                fired = int(pm["fee_only"].get("cf_fired_count") or 0)
            elif pm:
                first_model = next(iter(pm.values()))
                if isinstance(first_model, dict):
                    fired = int(first_model.get("cf_fired_count") or 0)
        per_strategy_fired[strat] = per_strategy_fired.get(strat, 0) + fired

    total_cf_fired = sum(per_strategy_fired.values())

    # Persist today's snapshot to daily/YYYYMMDD.json for trend / ETA computation.
    # 持久化今日 snapshot 到 daily/YYYYMMDD.json 供趨勢 / ETA 計算。
    today_key = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    try:
        daily_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = daily_dir / f"{today_key}.json"
        snapshot = {
            "utc_date": today_key,
            "recorded_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            "source_json_mtime": mtime.isoformat(timespec="seconds"),
            "n_rows": n_rows,
            "total_cf_fired": total_cf_fired,
            "per_strategy_rows": per_strategy_rows,
            "per_strategy_fired": per_strategy_fired,
        }
        with snapshot_path.open("w") as f:
            json.dump(snapshot, f, indent=2)
    except Exception as e:
        # Fail-soft on daily persist failure — don't turn the whole check red.
        # 快照寫入失敗 fail-soft，不讓整個 check 紅。
        pass

    # Phase 3 entry criteria evaluation.
    # Phase 3 入場條件判定。
    grid_fired = per_strategy_fired.get("grid_trading", 0)
    ma_fired = per_strategy_fired.get("ma_crossover", 0)
    orphan_rows = per_strategy_rows.get("orphan_frozen", 0)

    criteria_ok = (
        n_rows >= 200
        and grid_fired >= 50
        and ma_fired >= 50
        and orphan_rows >= 20
    )
    base_msg = (
        f"post-P013-clean n_rows={n_rows}, cf_fired={total_cf_fired}, "
        f"grid_fired={grid_fired}, ma_fired={ma_fired}, "
        f"orphan_frozen_rows={orphan_rows}, json_age={age_hours:.1f}h"
    )

    if criteria_ok:
        return ("PASS",
                base_msg + " — Phase 3 go: strategy-scoped deploy criteria satisfied, "
                "see TODO §EDGE-DIAG-1 Phase 3")

    # Compute rate & ETA from daily snapshots (need ≥2 points).
    # 用 daily snapshots 計算速率與 ETA（需 ≥2 個點）。
    rate_per_day = 30.0  # static fallback
    rate_source = "static-30/day"
    prev_rows: int | None = None
    try:
        if daily_dir.exists():
            snapshots = sorted(daily_dir.glob("*.json"))
            # Exclude today's snapshot we just wrote; we want HISTORICAL points.
            # 排除剛寫入的今日 snapshot；僅取歷史點。
            historical = [p for p in snapshots if p.stem != today_key]
            if len(historical) >= 1:
                # Use oldest + newest-historical as two anchors.
                # 用最舊 + 最新歷史點作兩錨點。
                try:
                    oldest_data = json.load(historical[0].open())
                    newest_data = json.load(historical[-1].open())
                    prev_rows = int(newest_data.get("n_rows") or 0)
                    if historical[0].stem != historical[-1].stem:
                        d0 = datetime.strptime(historical[0].stem, "%Y%m%d")
                        d1 = datetime.strptime(historical[-1].stem, "%Y%m%d")
                        days = max(1, (d1 - d0).days)
                        delta = int(newest_data.get("n_rows") or 0) - int(oldest_data.get("n_rows") or 0)
                        if delta > 0:
                            rate_per_day = delta / days
                            rate_source = f"observed {delta}rows/{days}d"
                except Exception:
                    pass
    except Exception:
        pass

    # Regression check: if we have a previous snapshot and today's n_rows decreased → FAIL.
    # 倒退檢查：若有前次 snapshot 且今日 n_rows 下降 → FAIL（資料清除 / writer regression）。
    if prev_rows is not None and n_rows < prev_rows:
        return ("FAIL",
                base_msg + f" — n_rows regressed from {prev_rows} (prior snapshot) "
                "— data purge or writer regression suspected")

    if n_rows == 0:
        return ("WARN",
                base_msg + f" — 0 rows yet; rate={rate_source}; "
                f"ETA ~{int(200 / max(rate_per_day, 1e-6))}d to 200")

    # On-track WARN with ETA to 200-row threshold.
    # 累積中 WARN，附 ETA 到 200-row 門檻。
    remaining = max(0, 200 - n_rows)
    pct = 100.0 * n_rows / 200.0
    eta_days = int(remaining / max(rate_per_day, 1e-6)) if remaining > 0 else 0
    return ("WARN",
            base_msg + f" — {n_rows}/200 ({pct:.0f}%), rate={rate_source}, "
            f"ETA ~{eta_days}d at current rate")


def check_edge_estimator_scheduler_fresh() -> tuple[str, str]:
    """[13] G6-02 (2026-04-24): edge_estimator_scheduler freshness + cell-count.

    MODULE_NOTE (EN): G1-01 / G4-04 mandatory passive-wait healthcheck per
    CLAUDE.md §七 rule (any "wait Nh / Nd" TODO must register a check). The
    2026-04-24 10-Agent audit Verified Finding #1 was that
    `settings/edge_estimates.json` had collapsed to **1 cell** with mtime 4d
    stale — scheduler had been silently dead despite uvicorn running. Existing
    check [7] catches the freshness side at 90-min granularity (and [7a]
    enforces a 10-cell floor as the 2026-04-24 fix), but G6-02 adds a stricter
    6-hour + 50-cell sibling threshold targeted at the G1-01 recovery path:
    while we wait for scheduler to repopulate the JSON to ≥50 cells (target
    coverage matching 5 strategies × 25 symbols ≈ 125 cells with sparse
    backoff), this check FAILs the moment the JSON drifts >6h or coverage
    crosses below 10 cells. Once G1-01 stabilises and JSON is consistently
    ≥50 cells, this becomes the steady-state passive-wait sentinel.

    Distinction vs [7] / [7a]:
      - [7]: 90-min freshness floor (scheduler hourly cadence) + structure
        validation + dormant-prefix breakdown. Catches "scheduler stopped"
        within ~90 min.
      - [7a]: 10-cell minimum floor (2026-04-24 G6-01). Catches
        "JSON written but coverage collapsed".
      - [13] (this check, G6-02): tighter 6h + 50-cell **target** threshold
        for G1-01 / G4-04 recovery monitoring. Three-state distinguishes
        "scheduler healthy + full coverage" (PASS) from "partial recovery"
        (WARN at 10-49 cells) from "still broken" (FAIL at <10 OR >6h).

    Three-state output:
      - PASS: mtime <6h AND populated cells ≥50 (full G1-01 recovery target).
      - WARN: 10 ≤ populated cells < 50 (partial coverage; backfill in progress).
      - FAIL: mtime ≥6h OR populated cells <10 (scheduler dead OR coverage
        collapse — G1-01 root cause not resolved).

    Reads `_meta.n_cells` first (introduced 2026-04-20+), falls back to
    counting non-meta entries (matches [7]'s flat-map walk pattern).

    [13] G6-02（2026-04-24）：edge_estimator_scheduler 新鮮度 + cell 數雙閾值
    （CLAUDE.md §七 G1-01 / G4-04 強制要求）。2026-04-24 10-Agent audit Verified
    Finding #1 = `settings/edge_estimates.json` 縮到 1 cell + mtime 4d 停滯。
    [7]/[7a] 已覆蓋 90min freshness + 10-cell 底線；[13] 新增更嚴的 6h + 50 cell
    目標閾值，作為 G1-01 復原期主信號：scheduler 重新填滿到 ≥50 cells 期間，
    此 check 在 JSON 漂移 >6h 或覆蓋 <10 cells 時立即 FAIL。
    三態：PASS（<6h + ≥50 cells，G1-01 復原目標）/ WARN（10-49 cells partial）/
    FAIL（>=6h OR <10 cells，scheduler 仍掛或 coverage 崩潰）。
    讀法：`_meta.n_cells` 優先（2026-04-20+ 新增），fallback 數非 meta entries。
    """
    # G6-02 thresholds — tighter than [7] (90 min / 10 cells); these are the
    # G1-01 / G4-04 recovery-target sentinels. Adjust upward to 100+ cells once
    # full strategy×symbol coverage is restored (5 strategies × 25 symbols).
    # G6-02 閾值：比 [7] (90min/10 cells) 更嚴，是 G1-01 / G4-04 復原目標哨兵。
    # 全策略×幣對覆蓋恢復後（5 策略 × 25 幣對）可上調到 100+ cells。
    MAX_AGE_HOURS = 6.0
    MIN_CELLS_PASS = 50
    MIN_CELLS_WARN = 10

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    p = base / "settings" / "edge_estimates.json"
    if not p.exists():
        return ("FAIL", f"edge_estimates.json 不存在 at {p} — scheduler never ran (G1-01)")

    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0

    # Parse cells: prefer `_meta.n_cells` (2026-04-20+ field), fall back to
    # walking the flat map (consistent with [7]'s walker for legacy JSON).
    # Cells 解析：`_meta.n_cells` 優先（2026-04-20+），fallback 走 flat map（與 [7] 一致）。
    n_cells: int | None = None
    parse_diag = ""
    try:
        data = json.load(p.open())
        meta = data.get("_meta") if isinstance(data, dict) else None
        if isinstance(meta, dict) and isinstance(meta.get("n_cells"), int):
            n_cells = int(meta["n_cells"])
            parse_diag = f"via _meta.n_cells={n_cells}"
        else:
            # Fallback: count non-meta dict entries (same logic as [7]).
            # Fallback：數非 meta dict entries（與 [7] 一致）。
            meta_keys = {"_meta", "grand_mean_bps", "generated_at", "n_total", "version"}
            cell_items = {
                k: v for k, v in data.items()
                if isinstance(v, dict) and not k.startswith("_") and k not in meta_keys
            }
            n_cells = len(cell_items)
            parse_diag = f"via flat-map walk={n_cells}"
    except Exception as e:
        # Parse failure: return FAIL because we cannot triage scheduler health
        # without cell count. Distinguish from [7] which WARNs on parse error
        # (because [7] still PASSes on freshness alone). G6-02 needs both signals.
        # Parse 失敗 FAIL：無 cell 數無法判 scheduler 狀態。與 [7] 區別：[7] 只
        # WARN（freshness 仍可單獨 PASS），G6-02 要兩個信號都齊。
        return ("FAIL",
                f"edge_estimates.json age {age_h:.1f}h, parse error: {e} — "
                "cannot triage scheduler health (G1-01)")

    msg_core = f"age={age_h:.1f}h, cells={n_cells} ({parse_diag})"

    # FAIL conditions (either dimension alone is enough).
    # FAIL 條件（任一 dimension 觸發即 FAIL）。
    if age_h >= MAX_AGE_HOURS:
        return ("FAIL",
                msg_core + f" — mtime ≥{MAX_AGE_HOURS}h (scheduler silent-dead; "
                "G1-01 root cause not resolved)")
    if n_cells < MIN_CELLS_WARN:
        return ("FAIL",
                msg_core + f" — cells <{MIN_CELLS_WARN} (coverage collapse; "
                "G1-01 / G4-04 recovery target not met)")

    # WARN: partial coverage band.
    # WARN：覆蓋恢復中。
    if n_cells < MIN_CELLS_PASS:
        return ("WARN",
                msg_core + f" — cells {n_cells}/{MIN_CELLS_PASS} (partial G1-01 "
                "recovery; backfill in progress)")

    # PASS: both dimensions meet G1-01 / G4-04 recovery target.
    # PASS：兩 dimension 皆達 G1-01 / G4-04 復原目標。
    return ("PASS",
            msg_core + f" — full G1-01 recovery target met (≥{MIN_CELLS_PASS} cells, "
            f"<{MAX_AGE_HOURS}h)")


def check_exit_features_accumulation_rate(cur) -> tuple[str, str]:
    """[14] G6-02 (2026-04-24): learning.exit_features weekly accumulation rate.

    MODULE_NOTE (EN): EDGE-P1b passive-wait healthcheck — the EDGE-P1b TODO
    waits for `learning.exit_features` to accumulate enough rows for ML
    training (per-strategy-symbol cell ≥ 200 labels). Without this check, a
    silent writer regression (e.g. paper_state hook deletion, schema_hash
    mismatch causing INSERT to be silently swapped to a no-op) could leave the
    table flat for days while the TODO still says "passive wait". This check
    compares this-week vs last-week row counts to catch acute decay.

    Compared to [3] `check_exit_features_writer` which validates the 24h
    1:1 ratio with close_fills, [14] adds a week-over-week trend signal:
      - [3] asks "is the writer firing right now per fill?"
      - [14] asks "is the writer's overall throughput consistent week to week?"
    Both can pass independently; both are needed because [3] catches per-fill
    misses (delta > 33% over 24h) and [14] catches longer-trend collapse
    (close_fills also dropped, so per-fill ratio still looks fine).

    Three-state output:
      - PASS: this_week > 0 AND this_week ≥ last_week × 0.5 (no severe decay).
      - WARN: this_week > 0 AND this_week < last_week × 0.3 (severe decay).
      - FAIL: this_week == 0 (writer completely silent — EDGE-P1b assumption
        violated; downstream ML training pipeline gates would silently stall).

    Edge case: last_week == 0 → if this_week > 0 the writer just started or
    came back from outage (PASS with note); if both 0 → FAIL (writer dead for
    ≥2 weeks).

    Filter: no engine_mode filter — exit_features writes for paper/demo/live_demo
    all matter for ML training corpus. Operator can grep for engine_mode
    breakdown via direct SQL if a specific engine looks anomalous.

    [14] G6-02（2026-04-24）：learning.exit_features 週環比累積速率守衛
    （EDGE-P1b TODO 被動等待 ML 訓練樣本累積到 per-cell ≥200 labels）。
    [3] 驗 24h per-fill 1:1 比率；[14] 補週環比趨勢信號。兩者互補：close_fills
    同步下降時 [3] 仍 PASS 但 [14] 抓長趨勢崩潰。三態：PASS（>0 且 ≥0.5×上週）/
    WARN（<0.3×上週）/ FAIL（this_week=0，writer 完全靜默 EDGE-P1b 假設破裂）。
    """
    # Defensive rollback: keep cursor clean.
    # 防禦式 rollback：保持 cursor 乾淨。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Table existence guard — same defensive pattern as [2]/[8]/[9].
    # 表存在性守衛 — 與 [2]/[8]/[9] 同模式。
    try:
        cur.execute("SELECT to_regclass('learning.exit_features') IS NOT NULL")
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"exit_features table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.exit_features missing — V999 not applied")

    # This week (last 7d) vs last week (8d-14d ago) row counts.
    # 本週（最近 7d）vs 上週（8d-14d 前）行數。
    try:
        cur.execute(
            "SELECT COUNT(*) FROM learning.exit_features "
            "WHERE ts > now() - interval '7 days'"
        )
        this_week = int(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COUNT(*) FROM learning.exit_features "
            "WHERE ts > now() - interval '14 days' "
            "AND ts <= now() - interval '7 days'"
        )
        last_week = int(cur.fetchone()[0] or 0)
    except Exception as e:
        return ("WARN", f"exit_features rate query failed: {e}")

    base = f"this_week={this_week}, last_week={last_week}"

    # FAIL: completely silent — EDGE-P1b assumption broken.
    # FAIL：完全靜默 — EDGE-P1b 假設破裂。
    if this_week == 0:
        if last_week == 0:
            return ("FAIL", base + " — writer dead ≥2 weeks (EDGE-P1b stalled; "
                    "check exit_feature_writer.rs + paper_state hook)")
        return ("FAIL", base + " — writer went silent this week "
                "(check exit_feature_writer.rs + Rust panic log)")

    # Special case: last_week == 0 but this_week > 0 → writer just started
    # or recovered from outage. Treat as PASS with note.
    # 特例：last_week=0 但 this_week>0 → writer 剛啟動或剛恢復。PASS + 註解。
    if last_week == 0:
        return ("PASS", base + " — writer recently activated "
                "(no historical baseline; defer trend evaluation 1 more week)")

    ratio = this_week / last_week

    # WARN: severe decay (< 30% of last week).
    # WARN：嚴重衰減（<30% 上週）。
    if ratio < 0.3:
        return ("WARN", base + f" (ratio={ratio:.2f}) — severe decay <30%; "
                "EDGE-P1b accumulation stalled, investigate fill rate + writer health")

    # WARN: moderate decay (30%-50% of last week).
    # WARN：中度衰減（30%-50% 上週）。
    if ratio < 0.5:
        return ("WARN", base + f" (ratio={ratio:.2f}) — moderate decay 30-50%; "
                "monitor next-week trend")

    # PASS: stable or growing.
    # PASS：穩定或成長。
    return ("PASS", base + f" (ratio={ratio:.2f}) — accumulation healthy")


def check_strategist_cycle_fresh() -> tuple[str, str]:
    """[16] G3-11 (2026-04-25 MVP): StrategistScheduler last cycle ≤10 min ago.

    MODULE_NOTE (EN): G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 passive-wait
    sentinel. The Rust scheduler runs a 5-min cycle (R3-1; backoff to 4h on
    AI service failure). Once the cycle wedges (engine restart that didn't
    re-spawn scheduler / Demo cmd channel orphan / panic in cycle body) the
    only operator-visible symptom is "applied params haven't moved in 24h",
    which is also the legitimate steady-state. Without this check, a wedged
    scheduler can hide for days.

    Implementation choice: filesystem-only via engine.log tail parse, NOT
    IPC. The IPC method `get_strategist_cycle_metrics` exists (G3-11 Rust
    side) but requires the HMAC handshake — pulling the auth secret into
    this script would couple the healthcheck to control-api wiring. Tail
    parsing matches existing footer fallback (
    /api/v1/strategist/history/cycle_metrics in
    `strategist_history_routes.py:_parse_cycle_metrics`) and has identical
    blind-spot profile (log rotation past N min → WARN/FAIL). Operator can
    run the GUI route in parallel for the structured snapshot.

    Three-state output:
      - PASS: scheduler logged a cycle (Ok or Err) within last 10 min, OR
        scheduler not bound (engine.log shows no startup line — Demo unbound
        is by design per memory `project_strategist_scheduler_paper_orphan`).
      - WARN: last cycle 10-30 min ago (within 30-min backoff window after
        first IPC failure — still healthy but degraded).
      - FAIL: last cycle >30 min ago AND scheduler was started.

    [16] G3-11（2026-04-25 MVP）：StrategistScheduler 上次 cycle ≤10 分鐘哨兵。
    Rust 5-min cycle wedge 後唯一外部症狀「24h 沒新 apply」也可能是穩態，
    本 check 用 engine.log tail parse 區分 wedged vs 穩態。
    PASS：10 分鐘內有 cycle log，或 scheduler 未綁（log 無啟動行）。
    WARN：10-30 分鐘（首次 IPC 失敗後 30-min backoff 仍健康但降級）。
    FAIL：>30 分鐘且 scheduler 啟動過。
    """
    log_path = Path(
        os.environ.get(
            "OPENCLAW_DATA_DIR",
            "/tmp/openclaw" if os.name != "nt" else str(Path.home() / "openclaw"),
        )
    ) / "engine.log"
    if not log_path.exists():
        return ("WARN", f"engine.log missing at {log_path} — cannot evaluate cycle freshness")
    try:
        # Bounded tail (last 4 MB) mirrors the GUI footer route. The
        # scheduler logs ~1 line per 5 min so 4 MB covers many days.
        # Bounded tail（最後 4 MB）對齊 GUI footer 路由；scheduler 每 5 min
        # 一行，4 MB 覆蓋多日。
        size = log_path.stat().st_size
        with log_path.open("rb") as f:
            if size > 4 * 1024 * 1024:
                f.seek(-4 * 1024 * 1024, 2)
                f.readline()  # discard partial line
            tail = f.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - filesystem race
        return ("WARN", f"engine.log read failed: {exc}")

    # Look for the most recent scheduler activity log. The Rust side emits:
    #   "StrategistScheduler started"  — once per spawn
    #   "StrategistScheduler cycle complete" — every successful cycle
    #   "StrategistScheduler cycle failed"   — every failed cycle
    #   "StrategistScheduler cancelled"      — shutdown
    # Pre-deploy of G3-11 the apply path emits "strategist params applied".
    # Match the broad family so we work pre/post G3-11 rebuild.
    # 比對所有 scheduler 活動行；廣域 match 讓 pre/post G3-11 部署都能用。
    started = "StrategistScheduler started" in tail or "策略師排程器已啟動" in tail
    activity_markers = (
        "StrategistScheduler cycle complete",
        "StrategistScheduler cycle failed",
        "strategist params applied",
        "evaluated_cycle",  # debug-level marker
        "策略師參數已應用",  # zh apply
    )

    # Find the latest matching log timestamp. Engine.log uses tracing's
    # default format with a leading RFC3339 timestamp.
    # 找最新匹配的 log 時戳；tracing 默認是 RFC3339 起頭。
    import re
    last_seen_dt: datetime | None = None
    pattern = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"
    )
    # Walk backwards through lines for efficiency on long tails.
    # 反向走訪行以加速長 tail 處理。
    for line in reversed(tail.splitlines()):
        if not any(marker in line for marker in activity_markers):
            continue
        m = pattern.match(line)
        if not m:
            continue
        try:
            last_seen_dt = datetime.fromisoformat(m.group("ts").replace("Z", "+00:00"))
            break
        except Exception:
            continue

    if last_seen_dt is None:
        if not started:
            return ("PASS",
                    "StrategistScheduler not started in tail — Demo unbound or fresh boot "
                    "(by design per project_strategist_scheduler_paper_orphan)")
        return ("FAIL",
                "scheduler started but no cycle activity in 4MB tail — wedged?")

    age_min = (datetime.now(tz=timezone.utc) - last_seen_dt).total_seconds() / 60.0
    if age_min < 0:
        # Clock skew — log timestamp is in the future. Pass with note.
        # 時鐘偏移 — log 時戳在未來。pass + note。
        return ("PASS", f"last cycle ts in future by {-age_min:.0f} min — clock skew")
    base = f"last cycle {age_min:.1f} min ago"
    if age_min <= 10.0:
        return ("PASS", base)
    if age_min <= 30.0:
        return ("WARN", f"{base} — within 30-min backoff window (first IPC failure?)")
    return ("FAIL", f"{base} — exceeds 30-min ceiling, scheduler likely wedged")


def check_shadow_exit_agreement_phase2(cur) -> tuple[str, str]:
    """[15] G6-02 (2026-04-24): Combine Layer shadow exit Python↔Rust agreement.

    MODULE_NOTE (EN): EDGE-P2 passive-wait healthcheck — the EDGE-P2 "flip
    shadow_enabled=true and observe N days" TODO requires that the Combine
    Layer (Python decision side) and the Physical-only baseline (Rust track P
    decision side) agree on ≥95% of close events. Without this check, the
    flip period could silently produce a divergent Combine vs Physical
    distribution that operator only notices at TODO sign-off (potentially
    days late).

    Note on column semantics: V021 schema does not have separate
    `decision_python` / `decision_rust` columns; the agreement signal is
    encoded in the `disagreed BOOLEAN` column (`disagreed=FALSE` means the
    Combine output matched what Physical-only would have produced — i.e.
    Python ↔ Rust agree). This check computes 1 - disagreed_ratio over the
    last 24h window. Phase 2 target ≥95% (this G6-02 check); existing [8]
    `check_shadow_exit_ratio` uses ≥60% as the soft entry-criterion floor.

    Three-state output:
      - PASS: 24h rows = 0 (Phase 1a dormant — shadow_enabled=false; deferred
        to [8]'s TOML-based triage), OR agreement ≥95%.
      - WARN: 80% ≤ agreement < 95% (Phase 2 below target but above
        intervention threshold; investigate disagreement_reason distribution).
      - FAIL: agreement < 80% (Combine layer materially diverging from
        Physical baseline; flip should be reverted, EDGE-P2 paused).

    Distinction vs [8] `check_shadow_exit_ratio`:
      - [8]: Phase 2 entry guard. Asks "is shadow_enabled=true and writer
        firing?" + "is agreement ≥60% soft floor?". Checks the TOML state
        machine + writer liveness.
      - [15]: Phase 2 quality gate. Asks "given shadow is firing, is the
        Combine agreement strict ≥95% target met?". No TOML check — relies
        on row presence to indicate Phase 2 is actively underway.

    [15] G6-02（2026-04-24）：Combine Layer shadow exit Python↔Rust 一致率守衛
    （EDGE-P2 flip 期被動等待 ≥95% agreement TODO）。V021 schema 用
    `disagreed BOOLEAN` 編碼一致性（FALSE=Combine 同 Physical baseline=Python ↔
    Rust agree）。本 check 算 24h 窗口 1 - disagreed_ratio。Phase 2 目標 ≥95%。
    與 [8] 區別：[8] 是入場守衛（TOML state + ≥60% 軟底線）；[15] 是品質閘
    （strict ≥95% 目標）。三態：PASS（24h=0 Phase 1a dormant，或 ≥95%）/
    WARN（80-95%）/ FAIL（<80% 且非空，Combine 材質性分歧 EDGE-P2 應回退）。
    """
    # Defensive rollback: keep cursor clean.
    # 防禦式 rollback：保持 cursor 乾淨。
    try:
        cur.connection.rollback()
    except Exception:
        pass

    # Table existence guard.
    # 表存在性守衛。
    try:
        cur.execute("SELECT to_regclass('learning.decision_shadow_exits') IS NOT NULL")
        exists = cur.fetchone()[0]
    except Exception as e:
        return ("FAIL", f"decision_shadow_exits table existence check failed: {e}")
    if not exists:
        return ("FAIL", "learning.decision_shadow_exits missing — V021 not applied")

    # 24h agreement query — `disagreed` BOOLEAN encodes Combine vs Physical
    # mismatch. Agreement = 1 - disagreed_ratio.
    # 24h agreement 查詢 — `disagreed` 編碼 Combine vs Physical 分歧。
    # Agreement = 1 - disagreed_ratio。
    try:
        cur.execute(
            "SELECT "
            "  COUNT(*)::int AS total, "
            "  COUNT(*) FILTER (WHERE disagreed = FALSE)::int AS agree_n "
            "FROM learning.decision_shadow_exits "
            "WHERE ts > now() - interval '24 hours'"
        )
        total, agree_n = cur.fetchone()
        total = int(total or 0)
        agree_n = int(agree_n or 0)
    except Exception as e:
        return ("WARN", f"shadow_exit agreement query failed: {e}")

    # Phase 1a dormant (shadow_enabled=false) — table empty by design.
    # Defer to [8] for the TOML-based triage; here we just pass with note.
    # Phase 1a dormant（shadow_enabled=false）— 表預期空，pass + note，
    # 細部 TOML triage 留給 [8]。
    if total == 0:
        return ("PASS",
                "decision_shadow_exits 24h=0 (Phase 1a dormant; agreement "
                "evaluation deferred until shadow_enabled=true — see [8])")

    agree_pct = 100.0 * agree_n / total
    base = f"24h_total={total}, agree={agree_n} ({agree_pct:.1f}%)"

    # FAIL: Combine layer materially diverging — EDGE-P2 should be paused.
    # FAIL：Combine 層材質性分歧 — EDGE-P2 應回退。
    if agree_pct < 80.0:
        return ("FAIL",
                base + " — agreement <80%; EDGE-P2 flip should be reverted "
                "(set [exit].shadow_enabled=false in risk_config_demo.toml + "
                "investigate disagreement_reason distribution)")

    # WARN: below 95% strict target but above intervention threshold.
    # WARN：低於 95% 嚴格目標但高於介入門檻。
    if agree_pct < 95.0:
        return ("WARN",
                base + " — Phase 2 target ≥95% not met; investigate "
                "disagreement_reason breakdown via SQL: "
                "SELECT disagreement_reason, COUNT(*) FROM "
                "learning.decision_shadow_exits WHERE disagreed=TRUE AND "
                "ts > now() - interval '24 hours' GROUP BY 1 ORDER BY 2 DESC")

    # PASS: ≥95% target met.
    # PASS：≥95% 目標達成。
    return ("PASS", base + " — Phase 2 ≥95% target met")


# ---- main ----

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="Only print non-PASS lines")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Passive-wait healthcheck @ {now} UTC")
    print("=" * 70)

    try:
        conn = _get_conn()
    except Exception as e:
        print(f"[FATAL] DB connect failed: {e}")
        return 2

    results: list[tuple[str, str, str]] = []  # (check_name, status, msg)
    try:
        with conn.cursor() as cur:
            # [1] baseline
            s, m, close_fills = check_close_fills_24h(cur)
            results.append(("[1] close_fills_24h", s, m))

            # [2] labels
            s, m = check_label_backfill_ratio(cur, close_fills)
            results.append(("[2] label_backfill", s, m))

            # [3] exit_features writer
            s, m = check_exit_features_writer(cur, close_fills)
            results.append(("[3] exit_features_writer", s, m))

            # [4] phys_lock
            s, m = check_phys_lock_runtime(cur)
            results.append(("[4] phys_lock_runtime", s, m))

            # [5] micro_profit
            s, m = check_micro_profit_fire(cur)
            results.append(("[5] micro_profit_fire", s, m))

            # [6] trailing stop
            s, m = check_trailing_stop_fire(cur)
            results.append(("[6] trailing_stop_fire", s, m))

            # [8] shadow_exits — INFRA-PREBUILD-1 Part A
            # Runs before conn.close(); [7] (filesystem-only) runs after.
            # [8] shadow_exits — INFRA-PREBUILD-1 A 部；在 conn.close 前跑。
            s, m = check_shadow_exit_ratio(cur)
            results.append(("[8] shadow_exits_24h", s, m))

            # [9] model_registry — INFRA-PREBUILD-1 Part B
            # Phase 1a/2 expected empty; [9] turns signal once Phase 3+ lands.
            # [9] model_registry — INFRA-PREBUILD-1 B 部；Phase 1a/2 預期空。
            s, m = check_model_registry_freshness(cur)
            results.append(("[9] model_registry_freshness", s, m))

            # [10] intents_writer_ratio — P1-12 post-mortem guard
            # Catches 4/17-style whole-table intents-writer silent outage.
            # [10] intents writer 比率守衛 — P1-12 post-mortem，防 4/17 事件復發。
            s, m = check_intents_writer_ratio(cur)
            results.append(("[10] intents_writer_ratio", s, m))

            # [12] bb_breakout_post_deadlock_fix — P1-11 (1) FIX-26-DEADLOCK-1
            # Once Rust commit bcc5401 deploys via --rebuild, bb_breakout
            # should exit "permanent dormant" state. Track real fill count.
            # [12] FIX-26-DEADLOCK-1 部署後 bb_breakout 是否脫離 permanent-dormant。
            s, m = check_bb_breakout_post_deadlock_fix(cur)
            results.append(("[12] bb_breakout_post_deadlock_fix", s, m))

            # [Xb] G6-01 (2026-04-24): pipeline triangulation covers QA §2.2 #4
            # "12 檢查彼此獨立，無 fills/labels/intents 三角形驗證". Uses the
            # close_fills from [1] as baseline anchor; cross-validates against
            # labels (same filter as [2]) and intents (same filter as [10]).
            # Runs inside the cursor block because it issues DB queries.
            # [Xb] G6-01（2026-04-24）：fills/labels/intents 三角驗證，彌補 QA
            # §2.2 #4 盲點。必須在 cursor 區塊內跑（會發 SQL）。
            s, m = check_pipeline_triangulation(cur, close_fills)
            results.append(("[Xb] pipeline_triangulation", s, m))

            # [14] G6-02 (2026-04-24): exit_features weekly accumulation rate —
            # EDGE-P1b passive-wait sentinel for ML-training row growth.
            # [14] G6-02（2026-04-24）：exit_features 週環比累積速率
            # — EDGE-P1b 被動等待 ML 訓練樣本累積守衛。
            s, m = check_exit_features_accumulation_rate(cur)
            results.append(("[14] exit_features_accumulation_rate", s, m))

            # [15] G6-02 (2026-04-24): shadow exit Combine vs Physical
            # agreement — EDGE-P2 Phase 2 quality gate (≥95% strict).
            # Phase 1a dormant when shadow_enabled=false (table empty → PASS).
            # [15] G6-02（2026-04-24）：shadow exit Combine vs Physical 一致率
            # — EDGE-P2 Phase 2 品質閘（≥95% 嚴格）。Phase 1a 空表 PASS。
            s, m = check_shadow_exit_agreement_phase2(cur)
            results.append(("[15] shadow_exit_agreement_phase2", s, m))
    finally:
        conn.close()

    # [7] filesystem check
    s, m = check_edge_estimates_freshness()
    results.append(("[7] edge_estimates_freshness", s, m))

    # [13] G6-02 (2026-04-24): edge_estimator_scheduler freshness +
    # cell-count combined sentinel (G1-01 / G4-04 recovery monitoring).
    # Tighter than [7] (6h vs 90min) + (50 cells vs 10 cells); both run
    # because [7] catches steady-state hourly cadence + dormant prefix
    # breakdown, [13] catches G1-01-class scheduler outage + coverage target.
    # [13] G6-02（2026-04-24）：edge_estimator_scheduler 雙閾值哨兵
    # （G1-01 / G4-04 復原監控）。比 [7] 嚴：6h vs 90min + 50 cells vs 10。
    # 兩個並存 — [7] 抓穩態小時節奏 + dormant prefix；[13] 抓 G1-01 級停滯。
    s, m = check_edge_estimator_scheduler_fresh()
    results.append(("[13] edge_estimator_scheduler_fresh", s, m))

    # [11] EDGE-DIAG-1 Phase 3 gate (cron-driven, filesystem-only).
    # Also self-bootstraps daily snapshot history in audit/daily/.
    # [11] EDGE-DIAG-1 Phase 3 gate（cron 驅動，純檔案系統 check）。
    # 同時自 bootstrap audit/daily/ 每日快照歷史。
    s, m = check_counterfactual_clean_window_growth()
    results.append(("[11] counterfactual_clean_window_growth", s, m))

    # [Xa] G6-01 (2026-04-24): leader-lock health for edge_estimator_scheduler
    # — covers the QA-flagged blind spot where check [7] alone cannot
    # distinguish a stale-lock dead leader from a busy scheduler.
    # [Xa] G6-01（2026-04-24）：edge_estimator_scheduler leader-lock 健康 —
    # 覆蓋 QA 指出的盲點：[7] 單獨無法區分 stale-lock 死 leader vs busy scheduler。
    s, m = check_leader_election_health()
    results.append(("[Xa] leader_election_health", s, m))

    # [16] G3-11 (2026-04-25 MVP): StrategistScheduler last cycle freshness via
    # engine.log tail parse. Catches wedged scheduler invisible to "applied
    # params haven't moved" steady-state observation. Pure filesystem (no DB,
    # no IPC HMAC) so kept outside the cur block.
    # [16] G3-11（2026-04-25 MVP）：StrategistScheduler last cycle 新鮮度
    # （engine.log tail parse），抓 wedge 而 "params 沒動" 看不出來的盲點。
    s, m = check_strategist_cycle_fresh()
    results.append(("[16] strategist_cycle_fresh", s, m))

    # [18] G2-06 (2026-04-26): disabled-strategy inventory — CLAUDE.md §三
    # drift 防線 (G6-04). Pure observability, always PASS — lists strategies
    # with [<name>].active=false in strategy_params_demo.toml so future
    # audits can't forget about them.
    # [18] G2-06（2026-04-26）：disabled 策略 inventory — CLAUDE.md §三 drift
    # 防線（G6-04）。純記錄性，永遠 PASS — 列出 demo TOML 中 active=false
    # 的策略，確保未來 audit 不會「忘了還有這策略」。
    s, m = check_disabled_strategy_inventory()
    results.append(("[18] disabled_strategy_inventory", s, m))

    # output
    any_fail = False
    any_warn = False
    for name, status, msg in results:
        if args.quiet and status == "PASS":
            continue
        print(f"{status:4s} {name:<36s} {msg}")
        if status == "FAIL":
            any_fail = True
        elif status == "WARN":
            any_warn = True

    print("=" * 70)
    if any_fail:
        print("SUMMARY: FAIL — ≥1 pipeline silent-dead，查 docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md")
        return 1
    if any_warn:
        print("SUMMARY: WARN — 非致命但需關注")
        return 0
    print("SUMMARY: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
