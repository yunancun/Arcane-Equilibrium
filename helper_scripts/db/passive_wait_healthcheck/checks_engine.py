"""Engine-flow healthchecks: [1] close_fills, [2] label backfill, [3] exit_features writer, [21] paper_state dust inventory.
引擎主流 healthcheck：[1] close_fills、[2] label backfill、[3] exit_features writer、[21] paper_state dust inventory。

MODULE_NOTE (EN): Extracted from the original ``passive_wait_healthcheck.py``
(lines 110-254 in the pre-split file). These checks form the fill-flow
baseline — every downstream ratio check (e.g. [Xb] triangulation, [10]
intents writer) anchors against [1]'s 24h close_fills count.

[21] ``check_paper_state_dust_inventory`` was added 2026-04-26 by the
PAPER-STATE-DUST-INVENTORY-MONITOR ticket (Tier 7 Track 2). It is the
post-EXIT-FEATURES-WRITER-BUG-1-FIX (commits af48ee1 + 83456e5) silent
regression sentinel: counts last-1h ``risk_close:fast_track%`` fills with
``realized_pnl=0`` (the dust-spiral fingerprint that Gate 1 USD floor
should now suppress to zero) plus the distinct-symbol fan-out. It
**supersedes** the narrower MICRO-PROFIT-FIX-1-HEALTHCHECK backlog
(MIT §6 follow-up #6) which only watched the exact-match
``= 'risk_close:fast_track_reduce_half'`` strategy_name; the new check
broadens to ``LIKE 'risk_close:fast_track%'`` (catches future fast_track
sub-tags), adds ``engine_mode IN ('demo','live','live_demo')`` to filter
paper-pipeline noise, and uses three-state PASS/WARN/FAIL verdict
instead of binary ``> 5 → FAIL``. Per PA Track 3 audit (commit
``dd4d64a``) §7.4 ready-to-deploy SQL + cross-env safety analysis (§8).

SQL strings, exit-code semantics, output formatting for [1][2][3] are
byte-identical to the pre-split version. [21] is pure SELECT, zero
mutation, fail-soft on PG unavail (per PA §8 cross-env hard requirement).

MODULE_NOTE (中): 從原 passive_wait_healthcheck.py 110-254 行抽出。
[1][2][3] 是 fill-flow 基線——下游所有比率 check（[Xb] triangulation /
[10] intents 等）皆錨在 [1] 的 24h close_fills。SQL / exit code / 輸出
格式與拆分前 byte-identical。

[21] ``check_paper_state_dust_inventory`` 為 2026-04-26 PAPER-STATE-DUST-
INVENTORY-MONITOR（Tier 7 Track 2）新增，為 EXIT-FEATURES-WRITER-BUG-1-FIX
（commits af48ee1 + 83456e5）後的 silent regression 哨兵：偵測過去 1h
``risk_close:fast_track%`` 且 ``realized_pnl=0`` 的 fill 計數（Gate 1
USD floor 修復後預期為 0）+ distinct symbol fan-out。本 check **supersedes**
更窄的 MICRO-PROFIT-FIX-1-HEALTHCHECK backlog（MIT §6 #6，只 exact-match
``risk_close:fast_track_reduce_half`` + 二態 ``> 5 → FAIL``）：擴展為
``LIKE 'risk_close:fast_track%'`` 以涵蓋未來 fast_track 子 tag、加
``engine_mode IN ('demo','live','live_demo')`` 過濾 paper noise、改三態
PASS/WARN/FAIL verdict。依據 PA Track 3 audit（commit ``dd4d64a``）
§7.4 ready-to-deploy SQL + §8 跨 env 安全性分析（純 SELECT、零 mutation、
PG 不可達 fail-soft）。
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


def check_paper_state_dust_inventory(cur) -> tuple[str, str]:
    """[21] paper_state dust inventory — EXIT-FEATURES-FIX silent-regression sentinel.

    PAPER-STATE-DUST-INVENTORY-MONITOR (PM Tier 7 Track 2, 2026-04-26).

    **What it watches**: counts last-1h fills with
    ``strategy_name LIKE 'risk_close:fast_track%'`` AND ``realized_pnl=0``
    (the dust-spiral fingerprint that EXIT-FEATURES-WRITER-BUG-1-FIX
    Gate 1 USD floor `ft_dust_qty_floor_usd=1.0` should now suppress to
    zero) plus the distinct-symbol fan-out (broader spiral path =
    new path emerged that Gate 1 misses). Filters
    ``engine_mode IN ('demo','live','live_demo')`` to exclude paper-pipeline
    noise (paper engine_mode='paper' may legitimately have residual dust
    activity; we only care about the production-grade pipelines).

    **Three-state verdict** (per PA Track 3 §7.4):
      * ``dust_spiral_count = 0`` → **PASS**
        (Gate 1 USD floor working as designed; no spiral activity)
      * ``1 <= dust_spiral_count <= 10 AND distinct_dust_symbols < 3``
        → **WARN** (Gate 1 may still be holding but dust path activity
        appearing — operator should investigate; possibly a new
        partial-reduce sub-tag, or Gate 1 `ft_dust_qty_floor_usd` set
        too low for some symbol)
      * ``dust_spiral_count > 10`` OR ``distinct_dust_symbols >= 3``
        → **FAIL** (Gate 1 not suppressing; either fix unset/regressed
        or a new spiral path emerged across multiple symbols — needs
        immediate RCA)

    **Why three-state** vs MIT §6 #6's binary ``> 5 → FAIL``: the
    cohesive EXIT-FEATURES-FIX A1+A3+B1 chain expects this count to be
    exactly 0 in steady state; any non-zero is informational (could be
    a transient at fix-deploy boundary, or a fresh spiral path appearing
    that we want to surface BEFORE it crosses the binary threshold).
    WARN gives operator a 10-event window to act before FAIL escalates.

    **Why `LIKE 'risk_close:fast_track%'`** vs MIT §6 #6's exact-match
    ``= 'risk_close:fast_track_reduce_half'``: future fast_track sub-tags
    (e.g. ``risk_close:fast_track_close_all``, ``risk_close:fast_track_sigma_scaled``)
    are caught automatically without needing this healthcheck to be
    re-edited per new tag.

    **Why ``engine_mode IN ('demo','live','live_demo')``** vs MIT §6 #6's
    no engine_mode filter: paper engine has separate cleanup semantics +
    legitimate residual dust activity by design (3E-ARCH paper pipeline);
    we only sentinel the live-grade pipelines where dust-spiral = real bug.

    **Cross-env safety** (per PA §8 hard requirement):
      * Pure SELECT, zero mutation
      * Fail-soft on PG unavail (psycopg2 exception → caller catches)
      * Idempotent (1h window slides, no state)
      * No IPC, no HMAC secret coupling — runs in cron / CI without setup

    **Supersedes** ``MICRO-PROFIT-FIX-1-HEALTHCHECK`` (TODO line ~502,
    MIT EXIT-FEATURES audit §6 #6 spec) — that ticket's narrower scope
    (exact strategy_name match, binary verdict, no engine_mode filter)
    is fully covered by this broader check + tighter classification.

    [21] paper_state dust inventory — EXIT-FEATURES-FIX silent regression 哨兵。
    PAPER-STATE-DUST-INVENTORY-MONITOR（PM Tier 7 Track 2，2026-04-26）。

    **監測對象**：過去 1h ``strategy_name LIKE 'risk_close:fast_track%'``
    且 ``realized_pnl=0`` 的 fill 計數（EXIT-FEATURES-WRITER-BUG-1-FIX
    Gate 1 USD floor `ft_dust_qty_floor_usd=1.0` 修復後預期應為 0
    — 這是 dust spiral 的指紋）+ distinct symbol fan-out（廣度擴大 =
    Gate 1 漏抓的新 path 出現）。`engine_mode IN ('demo','live','live_demo')`
    過濾掉 paper pipeline 噪音（paper 有獨立 cleanup 語意）。

    **三態 verdict**（per PA Track 3 §7.4）：
      * 計數 = 0 → **PASS**（Gate 1 USD floor 工作中，無 spiral 跡象）
      * 1-10 + distinct_symbols < 3 → **WARN**（Gate 1 可能還抓住但有
        dust path 活動 — operator 需查；可能是新 partial-reduce 子 tag，
        或某 symbol 的 Gate 1 floor 設太低）
      * > 10 OR distinct_symbols >= 3 → **FAIL**（Gate 1 沒擋住；
        修復不見了/regressed 或新 spiral path 跨多 symbol 出現 — 需立即 RCA）

    **為何三態 vs MIT §6 #6 二態 `> 5 → FAIL`**：cohesive EXIT-FEATURES-FIX
    A1+A3+B1 鏈在穩態下預期此計數為 exactly 0；任何非零都是訊息
    （可能是修復部署邊界 transient，或新 spiral path 出現需在跨二態
    閾值前 surface）。WARN 給 operator 10-event 窗口在 FAIL escalate 前先動。

    **為何 `LIKE 'risk_close:fast_track%'` vs MIT exact-match**：未來
    fast_track 子 tag（如 close_all、sigma_scaled）自動覆蓋，無需逐 tag
    回來改 healthcheck。

    **為何 engine_mode 過濾 vs MIT 無過濾**：paper engine 有獨立 cleanup
    語意 + 設計上有合法的殘留 dust 活動（3E-ARCH paper pipeline）；
    我們只哨兵 live-grade pipeline，dust-spiral = 真 bug。

    **跨 env 安全**（per PA §8 hard requirement）：純 SELECT、零 mutation、
    PG 不可達 fail-soft（psycopg2 例外由 caller 接）、idempotent（1h
    滑動窗無狀態）、無 IPC、無 HMAC secret coupling — cron / CI 直接跑無前置設定。

    **Supersedes** ``MICRO-PROFIT-FIX-1-HEALTHCHECK``（TODO line ~502，
    MIT EXIT-FEATURES audit §6 #6 spec）— 該 ticket 較窄 scope
    (exact strategy_name、二態、無 engine_mode 過濾) 完全被本 check
    更廣 SQL + 更細 verdict 涵蓋。
    """
    # PA Track 3 §7.4 ready-to-deploy SQL — pure SELECT, FILTER on realized_pnl
    # to compute (a) total dust-spiral fill count, (b) distinct symbol fan-out
    # in a single round-trip.
    # PA Track 3 §7.4 ready-to-deploy SQL — 純 SELECT，FILTER 計算
    # (a) dust-spiral 總計數 + (b) distinct symbol 擴散度，單次 round-trip。
    cur.execute(
        "SELECT "
        "  COUNT(*) FILTER (WHERE realized_pnl = 0) AS dust_spiral_count, "
        "  COUNT(DISTINCT symbol) FILTER (WHERE realized_pnl = 0) AS distinct_dust_symbols "
        "FROM trading.fills "
        "WHERE strategy_name LIKE 'risk_close:fast_track%' "
        "  AND ts > now() - interval '1 hour' "
        "  AND engine_mode IN ('demo', 'live', 'live_demo')"
    )
    row = cur.fetchone()
    # Defensive: psycopg2 returning None on cursor failure (shouldn't happen
    # with our DSN config but the fail-soft contract requires it).
    # 防禦：psycopg2 cursor 失敗回 None（DSN config 下不應發生但 fail-soft
    # contract 要求處理）。
    if row is None:
        return ("WARN", "dust inventory query returned no row (PG / cursor anomaly)")

    dust_count = int(row[0]) if row[0] is not None else 0
    distinct_symbols = int(row[1]) if row[1] is not None else 0

    base_msg = (
        f"dust_spiral_count={dust_count} (last 1h, "
        f"strategy LIKE 'risk_close:fast_track%' AND realized_pnl=0 "
        f"AND engine_mode IN demo/live/live_demo), distinct_symbols={distinct_symbols}"
    )

    # Three-state verdict per PA Track 3 §7.4
    # 三態 verdict per PA Track 3 §7.4
    if dust_count == 0:
        return ("PASS", base_msg + " — Gate 1 USD floor suppressing as designed")

    if dust_count > 10 or distinct_symbols >= 3:
        return (
            "FAIL",
            base_msg
            + " — Gate 1 not suppressing OR new spiral path across symbols; "
            + "RCA EXIT-FEATURES-FIX A1/A3/B1 regression",
        )

    # 1 <= dust_count <= 10 AND distinct_symbols < 3
    return (
        "WARN",
        base_msg + " — dust path activity appearing; investigate before threshold escalates",
    )
