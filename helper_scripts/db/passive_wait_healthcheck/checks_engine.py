"""Engine-flow healthchecks: [1] close_fills, [2] label backfill, [3] exit_features writer.
引擎主流 healthcheck：[1] close_fills、[2] label backfill、[3] exit_features writer。

MODULE_NOTE (EN): Extracted from the original ``passive_wait_healthcheck.py``
(lines 110-254 in the pre-split file). These three checks form the
fill-flow baseline — every downstream ratio check (e.g. [Xb]
triangulation, [10] intents writer) anchors against [1]'s 24h
close_fills count.

SQL strings, exit-code semantics, output formatting are byte-identical
to the pre-split version.

MODULE_NOTE (中): 從原 passive_wait_healthcheck.py 110-254 行抽出。
此三個 check 是 fill-flow 基線——下游所有比率 check（[Xb] triangulation /
[10] intents 等）皆錨在 [1] 的 24h close_fills。SQL / exit code / 輸出
格式與拆分前 byte-identical。
"""

from __future__ import annotations

from .db import _scalar


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
